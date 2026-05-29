import unittest

from laffyhand.agent.schemas import SystemMessage, UserMessage, ToolMessage
from laffyhand.agent.loop import _wrap_last_user, _attach_reminder


class TestWrapLastUser(unittest.TestCase):
    def test_wraps_last_user_message(self):
        msgs = [SystemMessage(content="sys"), UserMessage(content="Continue if you have next steps")]
        _wrap_last_user(msgs)
        self.assertTrue(msgs[1].content.startswith("<system-reminder>"))
        self.assertTrue(msgs[1].content.endswith("</system-reminder>"))

    def test_no_user_message(self):
        msgs = [SystemMessage(content="sys")]
        _wrap_last_user(msgs)
        self.assertEqual(len(msgs), 1)

    def test_empty_messages(self):
        msgs: list = []
        _wrap_last_user(msgs)
        self.assertEqual(len(msgs), 0)

    def test_does_not_double_wrap(self):
        msgs = [UserMessage(content="<system-reminder>\nalready wrapped\n</system-reminder>")]
        _wrap_last_user(msgs)
        self.assertEqual(msgs[0].content.count("<system-reminder>"), 1)

    def test_only_wraps_last_user(self):
        msgs = [
            SystemMessage(content="sys"),
            UserMessage(content="first user"),
            ToolMessage(tool_call_id="c1", content="tool result"),
            UserMessage(content="second user"),
        ]
        _wrap_last_user(msgs)
        self.assertEqual(msgs[1].content, "first user")
        self.assertTrue(msgs[3].content.startswith("<system-reminder>"))


class TestAttachReminder(unittest.TestCase):
    def test_reminder_appended_to_system(self):
        msgs = [SystemMessage(content="original prompt")]
        _attach_reminder(msgs, "REMINDER: be concise")
        self.assertIn("REMINDER: be concise", msgs[0].content)

    def test_no_system_message(self):
        msgs = [UserMessage(content="hi")]
        _attach_reminder(msgs, "REMINDER: text")
        self.assertEqual(len(msgs), 1)

    def test_no_duplicate_reminder(self):
        msgs = [SystemMessage(content="prompt")]
        _attach_reminder(msgs, "REMINDER: text")
        _attach_reminder(msgs, "REMINDER: text")
        self.assertEqual(msgs[0].content.count("REMINDER: text"), 1)

    def test_empty_messages(self):
        msgs: list = []
        _attach_reminder(msgs, "REMINDER: test")
        self.assertEqual(len(msgs), 0)
