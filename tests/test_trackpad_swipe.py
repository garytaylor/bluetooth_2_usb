import unittest

from bluetooth_2_usb.relay.magic_trackpad import _SpacesSwipe


class SpacesSwipeTest(unittest.TestCase):
    def test_completed_horizontal_four_finger_swipes(self):
        for fingers, dx, dy, cancelled, expected in [
            (4, -300, 10, False, "right"),
            (4, 300, 0, False, "left"),
            (4, 300, 250, False, None),
            (4, 100, 0, False, None),
            (3, 300, 0, False, None),
            (4, 300, 0, True, None),
        ]:
            with self.subTest(fingers=fingers, dx=dx, dy=dy, cancelled=cancelled):
                swipe = _SpacesSwipe()
                swipe.begin(fingers)
                swipe.update(dx, dy)
                self.assertEqual(swipe.end(cancelled), expected)
                self.assertIsNone(swipe.end(False))
