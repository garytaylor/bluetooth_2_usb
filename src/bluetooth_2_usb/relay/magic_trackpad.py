"""Translate only the Apple Magic Trackpad into evdev mouse frames."""

import asyncio
import ctypes as C
import math
import os
from functools import cache

from ..evdev import ecodes
from ..evdev.types import InputEvent

_DEVICE_REMOVED = 2
_SWIPE_BEGIN, _SWIPE_UPDATE, _SWIPE_END = 800, 801, 802
_MIN_SWIPE_DISTANCE = 250  # libinput unaccelerated motion units
_POINTER_MOTION = 400
_POINTER_BUTTON = 402
_POINTER_SCROLL_FINGER = 405
_SCROLL_VERTICAL = 0
_SCROLL_HORIZONTAL = 1
_SCROLL_UNITS_PER_DETENT = 15.0
_POINTER_SCALE = 0.75

_Open = C.CFUNCTYPE(C.c_int, C.c_char_p, C.c_int, C.c_void_p)
_Close = C.CFUNCTYPE(None, C.c_int, C.c_void_p)


@_Open
def _open_device(path, flags, _data):
    try:
        return os.open(path, flags)
    except OSError as error:
        return -error.errno


@_Close
def _close_device(fd, _data):
    os.close(fd)


class _Interface(C.Structure):
    _fields_ = [("open_restricted", _Open), ("close_restricted", _Close)]


_INTERFACE = _Interface(_open_device, _close_device)


@cache
def _load_api():
    lib = C.CDLL("libinput.so.10")
    pointer, integer, number = C.c_void_p, C.c_int, C.c_double
    signatures = {
        "path_create_context": (pointer, C.POINTER(_Interface), pointer),
        "path_add_device": (pointer, pointer, C.c_char_p),
        "get_fd": (integer, pointer),
        "dispatch": (integer, pointer),
        "get_event": (pointer, pointer),
        "event_get_type": (integer, pointer),
        "event_get_pointer_event": (pointer, pointer),
        "event_pointer_get_dx": (number, pointer),
        "event_pointer_get_dy": (number, pointer),
        "event_pointer_get_button": (C.c_uint32, pointer),
        "event_pointer_get_button_state": (integer, pointer),
        "event_pointer_has_axis": (integer, pointer, integer),
        "event_pointer_get_scroll_value": (number, pointer, integer),
        "event_get_gesture_event": (pointer, pointer),
        "event_gesture_get_finger_count": (integer, pointer),
        "event_gesture_get_dx_unaccelerated": (number, pointer),
        "event_gesture_get_dy_unaccelerated": (number, pointer),
        "event_gesture_get_cancelled": (integer, pointer),
        "event_destroy": (None, pointer),
        "unref": (pointer, pointer),
    }
    for name, (result, *arguments) in signatures.items():
        function = getattr(lib, "libinput_" + name)
        function.restype = result
        function.argtypes = arguments
        setattr(lib, name, function)
    return lib


def libinput_available():
    try:
        _load_api()
    except (OSError, AttributeError):
        return False
    return True


class _SpacesSwipe:
    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.x = self.y = 0.0

    def begin(self, fingers):
        self.reset()
        self.active = fingers == 4

    def update(self, dx, dy):
        if self.active:
            self.x += dx
            self.y += dy

    def end(self, cancelled):
        x, y, active = self.x, self.y, self.active
        self.reset()
        if active and not cancelled and abs(x) >= _MIN_SWIPE_DISTANCE and abs(x) > 1.5 * abs(y):
            # A swipe left moves the current desktop left, exposing the next Space.
            return "right" if x < 0 else "left"
        return None


async def mouse_events(path, switch_space=None):
    lib = _load_api()
    context = lib.path_create_context(C.byref(_INTERFACE), None)
    if not context:
        raise OSError("Could not initialize libinput")
    fd = None
    registered = False
    loop = asyncio.get_running_loop()
    ready = asyncio.Event()
    remainder = {}
    pressed = set()
    swipe = _SpacesSwipe()

    def delta(code, value):
        total = remainder.get(code, 0.0) + value
        whole = math.trunc(total)
        remainder[code] = total - whole
        return InputEvent(0, 0, ecodes.EV_REL, code, whole) if whole else None

    try:
        if not lib.path_add_device(context, os.fsencode(path)):
            raise OSError(f"libinput declined touchpad {path}")
        fd = lib.get_fd(context)
        loop.add_reader(fd, ready.set)
        registered = True
        ready.set()
        while True:
            await ready.wait()
            ready.clear()
            result = lib.dispatch(context)
            if result < 0:
                raise OSError(-result, os.strerror(-result))
            while event := lib.get_event(context):
                frame = []
                space = None
                try:
                    kind = lib.event_get_type(event)
                    if switch_space and kind in (_SWIPE_BEGIN, _SWIPE_UPDATE, _SWIPE_END):
                        gesture = lib.event_get_gesture_event(event)
                        if kind == _SWIPE_BEGIN:
                            swipe.begin(lib.event_gesture_get_finger_count(gesture))
                        elif kind == _SWIPE_UPDATE:
                            swipe.update(
                                lib.event_gesture_get_dx_unaccelerated(gesture),
                                lib.event_gesture_get_dy_unaccelerated(gesture),
                            )
                        else:
                            space = swipe.end(lib.event_gesture_get_cancelled(gesture))
                    if kind in (_POINTER_MOTION, _POINTER_BUTTON, _POINTER_SCROLL_FINGER):
                        pointer = lib.event_get_pointer_event(event)
                        if kind == _POINTER_MOTION:
                            frame = [
                                delta(ecodes.REL_X, lib.event_pointer_get_dx(pointer) * _POINTER_SCALE),
                                delta(ecodes.REL_Y, lib.event_pointer_get_dy(pointer) * _POINTER_SCALE),
                            ]
                        elif kind == _POINTER_BUTTON:
                            code = lib.event_pointer_get_button(pointer)
                            if code in (ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MIDDLE):
                                state = lib.event_pointer_get_button_state(pointer)
                                if state:
                                    pressed.add(code)
                                else:
                                    pressed.discard(code)
                                frame = [InputEvent(0, 0, ecodes.EV_KEY, code, state)]
                        else:
                            for axis, code, direction in (
                                (_SCROLL_VERTICAL, ecodes.REL_WHEEL_HI_RES, 1),
                                (_SCROLL_HORIZONTAL, ecodes.REL_HWHEEL_HI_RES, -1),
                            ):
                                if lib.event_pointer_has_axis(pointer, axis):
                                    value = lib.event_pointer_get_scroll_value(pointer, axis)
                                    frame.append(delta(code, direction * value * 120 / _SCROLL_UNITS_PER_DETENT))
                finally:
                    lib.event_destroy(event)
                if space is not None:
                    await switch_space(space)
                if kind == _DEVICE_REMOVED:
                    for code in pressed:
                        yield InputEvent(0, 0, ecodes.EV_KEY, code, 0)
                    return
                emitted = False
                for item in frame:
                    if item is not None:
                        yield item
                        emitted = True
                if emitted:
                    yield InputEvent(0, 0, ecodes.EV_SYN, ecodes.SYN_REPORT, 0)
    finally:
        if registered:
            loop.remove_reader(fd)
        lib.unref(context)
