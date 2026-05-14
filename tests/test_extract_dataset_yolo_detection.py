import unittest

from tools.extract_dataset_yolo_detection import (
    CATEGORY_TO_CLASS,
    CLASS_NAMES,
    make_output_stem,
    normalize_yolo_bbox,
)


class YoloDetectionExtractionTests(unittest.TestCase):
    def test_normalize_yolo_bbox_converts_coco_bbox_to_yolo_coordinates(self):
        result = normalize_yolo_bbox([10, 20, 30, 40], image_width=100, image_height=200)

        self.assertEqual(result, (0.25, 0.2, 0.3, 0.2))

    def test_normalize_yolo_bbox_rejects_invalid_boxes(self):
        self.assertIsNone(normalize_yolo_bbox([10, 20, 0, 40], image_width=100, image_height=200))
        self.assertIsNone(normalize_yolo_bbox([95, 20, 20, 40], image_width=100, image_height=200))

    def test_class_order_preserves_existing_frame_detection_ids(self):
        self.assertEqual(
            CLASS_NAMES,
            [
                "hemming",
                "hole_deform",
                "outer_damage",
                "sealing",
                "gap_defect",
                "fastening_defect",
            ],
        )
        self.assertEqual(CATEGORY_TO_CLASS[212], 0)
        self.assertEqual(CATEGORY_TO_CLASS[213], 1)
        self.assertEqual(CATEGORY_TO_CLASS[102], 2)
        self.assertEqual(CATEGORY_TO_CLASS[204], 3)
        self.assertEqual(CATEGORY_TO_CLASS[207], 4)
        self.assertEqual(CATEGORY_TO_CLASS[209], 5)

    def test_make_output_stem_is_stable_and_unique_enough_for_tar_members(self):
        first = make_output_stem("frame", "frame/class/sample.jpg")
        second = make_output_stem("frame", "frame/other/sample.jpg")

        self.assertTrue(first.startswith("frame_sample_"))
        self.assertTrue(second.startswith("frame_sample_"))
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
