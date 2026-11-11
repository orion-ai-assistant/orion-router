import unittest

from database.manager import merge_item_config


class GroupItemSettingsTests(unittest.TestCase):
    """A group item holds no copy of its model: the model's current settings, with only the item's own on top."""

    def test_an_item_without_settings_is_the_model_as_it_is_now(self):
        model = {"local_sampling": {"top_p": 0.95, "top_k": 64}, "voice": "c1"}
        self.assertEqual(merge_item_config(model, None), model)
        self.assertEqual(merge_item_config('{"voice": "c1"}', "{}"), {"voice": "c1"})

    def test_an_item_override_replaces_only_what_it_sets(self):
        model = {"local_sampling": {"top_p": 0.95, "top_k": 64, "min_p": 0.05}, "voice": "c1"}
        merged = merge_item_config(model, {"local_sampling": {"top_k": 20}})
        self.assertEqual(merged["local_sampling"], {"top_p": 0.95, "top_k": 20, "min_p": 0.05})
        self.assertEqual(merged["voice"], "c1")

    def test_one_engines_override_leaves_the_rest_of_the_tts_settings(self):
        model = {"per_engine": {"voxcpm2": {"voice": "c1", "steps": "15"}, "omnivoice": {"seed": "7"}}}
        merged = merge_item_config(model, {"per_engine": {"voxcpm2": {"steps": "30"}}})
        self.assertEqual(merged["per_engine"], {"voxcpm2": {"voice": "c1", "steps": "30"}, "omnivoice": {"seed": "7"}})

    def test_other_settings_are_replaced_whole(self):
        # A thinking schema is one setting: the item's is used as it is, not mixed with the model's.
        model = {"thinking_schema": {"type": "budget", "min": 1, "max": 8192}}
        merged = merge_item_config(model, {"thinking_schema": {"type": "level", "options": ["low"]}})
        self.assertEqual(merged["thinking_schema"], {"type": "level", "options": ["low"]})

    def test_the_model_is_not_changed(self):
        model = {"local_sampling": {"top_p": 0.95}}
        merge_item_config(model, {"local_sampling": {"top_p": 0.5}})
        self.assertEqual(model, {"local_sampling": {"top_p": 0.95}})


if __name__ == "__main__":
    unittest.main()
