import unittest

from laffyhand.agent.schemas import SystemMessage, UserMessage, ToolMessage
from laffyhand.agent.compaction import wrap_last_user, attach_reminder


class TestWrapLastUser(unittest.TestCase):
    def test_wraps_last_user_message(self):
        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="Continue if you have next steps"),
        ]
        result = wrap_last_user(msgs)
        self.assertTrue(result[1].content.startswith("<system-reminder>"))
        self.assertTrue(result[1].content.endswith("</system-reminder>"))

    def test_no_user_message(self):
        msgs = [SystemMessage(content="sys")]
        result = wrap_last_user(msgs)
        self.assertEqual(len(result), 1)

    def test_empty_messages(self):
        msgs: list = []
        result = wrap_last_user(msgs)
        self.assertEqual(len(result), 0)

    def test_does_not_double_wrap(self):
        msgs = [
            UserMessage(
                content="<system-reminder>\nalready wrapped\n</system-reminder>"
            )
        ]
        result = wrap_last_user(msgs)
        self.assertEqual(result[0].content.count("<system-reminder>"), 1)

    def test_only_wraps_last_user(self):
        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="first user"),
            ToolMessage(tool_call_id="c1", content="tool result"),
            UserMessage(content="second user"),
        ]
        result = wrap_last_user(msgs)
        self.assertEqual(result[1].content, "first user")
        self.assertTrue(result[3].content.startswith("<system-reminder>"))
        self.assertEqual(msgs[3].content, "second user", "should not mutate original")


class TestAttachReminder(unittest.TestCase):
    def test_reminder_appended_to_system(self):
        msgs = [SystemMessage(content="original prompt")]
        result = attach_reminder(msgs, "REMINDER: be concise")
        self.assertIn("REMINDER: be concise", result[0].content)

    def test_no_system_message(self):
        msgs = [UserMessage(content="hi")]
        result = attach_reminder(msgs, "REMINDER: text")
        self.assertEqual(len(result), 1)

    def test_no_duplicate_reminder(self):
        msgs = [SystemMessage(content="prompt")]
        result = attach_reminder(msgs, "REMINDER: text")
        result = attach_reminder(result, "REMINDER: text")
        self.assertEqual(result[0].content.count("REMINDER: text"), 1)

    def test_empty_messages(self):
        msgs: list = []
        result = attach_reminder(msgs, "REMINDER: test")
        self.assertEqual(len(result), 0)
