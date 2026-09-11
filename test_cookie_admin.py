import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from cookie_admin import CookieAdmin
from telegram.ext import ApplicationHandlerStop


def update(user=42, chat=42, kind='private'):
    message = NS(reply_text=AsyncMock(), delete=AsyncMock(),
                 document=NS(file_name='cookies.txt', file_size=128, file_id='file'))
    return NS(effective_user=NS(id=user), effective_chat=NS(id=chat, type=kind),
              effective_message=message, callback_query=NS(data='cookies:instagram', answer=AsyncMock()))


class AdminTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.admin = CookieAdmin(AsyncMock(return_value=42))
        self.admin.api = AsyncMock(return_value={'platforms': {}})
        self.context = NS(args=[], bot=NS(send_message=AsyncMock(), get_file=AsyncMock()))

    async def test_unauthorized_and_group_cannot_use_any_action(self):
        for u in (update(user=7), update(chat=-123, kind='group')):
            await self.admin.command(u, self.context)
            await self.admin.callback(u, self.context)
            self.admin.pending[42] = ('instagram', time.monotonic() + 100)
            await self.admin.document(u, self.context)
            u.effective_message.reply_text.assert_not_awaited()
        self.admin.api.assert_not_awaited()
        self.context.bot.get_file.assert_not_awaited()

    async def test_effective_admin_override_select_and_cancel(self):
        u = update()
        await self.admin.callback(u, self.context)
        self.assertEqual(self.admin.pending[42][0], 'instagram')
        u.callback_query.data = 'cookies:cancel'
        await self.admin.callback(u, self.context)
        self.assertNotIn(42, self.admin.pending)

    async def test_upload_saved_remotely_and_retry_on_failure(self):
        u = update()
        self.admin.pending[42] = ('instagram', time.monotonic() + 100)
        file = NS(download_as_bytearray=AsyncMock(return_value=b'cookie-data'))
        self.context.bot.get_file.return_value = file
        self.admin.api.side_effect = RuntimeError('Render non disponibile')
        await self.admin.document(u, self.context)
        self.assertIn(42, self.admin.pending)
        self.context.bot.send_message.assert_not_awaited()
        self.admin.api.side_effect = None
        self.admin.api.return_value = {'ok': True}
        await self.admin.document(u, self.context)
        self.admin.api.assert_awaited_with('PUT', 'instagram', 'cookie-data')
        self.assertNotIn(42, self.admin.pending)
        self.assertEqual(self.context.bot.send_message.call_args.args[0], 42)

    async def test_alert_only_private_dedup_and_retry_failed_send(self):
        self.admin.api.return_value = {'platforms': {
            'instagram': {'state': 'expired', 'version': 'v1'},
            'youtube': {'state': 'present', 'version': 'v2'},
            'facebook': {'state': 'missing', 'version': 'v3'}}}
        self.context.bot.send_message.side_effect = RuntimeError()
        await self.admin.check(self.context)
        self.assertEqual(self.admin.alerts, {})
        self.context.bot.send_message.side_effect = None
        await self.admin.check(self.context)
        await self.admin.check(self.context)
        self.assertEqual(self.context.bot.send_message.await_count, 2)
        self.assertEqual(self.context.bot.send_message.call_args.args[0], 42)
        buttons = self.context.bot.send_message.call_args.kwargs['reply_markup']
        self.assertEqual(buttons.inline_keyboard[0][0].callback_data, 'cookies:instagram')

    async def test_negative_admin_never_sends_group_alert(self):
        self.admin.admin_id.return_value = -123
        await self.admin.check(self.context)
        self.admin.api.assert_not_awaited()

    async def test_paste_multiple_messages_saved_only_by_admin_button(self):
        u = update()
        await self.admin.select(u, 'instagram')
        for text in ('# Netscape HTTP Cookie File', '.instagram.com\tTRUE\t/\tTRUE\t4102444800\tsessionid\tSECRET'):
            u.effective_message.text = text
            with self.assertRaises(ApplicationHandlerStop):
                await self.admin.capture_text(u, self.context)
        self.admin.api.assert_not_awaited()
        self.assertEqual(u.effective_message.delete.await_count, 2)
        u.callback_query.data = 'cookies:save'
        await self.admin.callback(u, self.context)
        self.admin.api.assert_awaited_once_with('PUT', 'instagram', '# Netscape HTTP Cookie File\n.instagram.com\tTRUE\t/\tTRUE\t4102444800\tsessionid\tSECRET')
        self.assertNotIn(42, self.admin.pasted)
        for call in u.effective_message.reply_text.call_args_list:
            self.assertNotIn('SECRET', call.args[0])

    async def test_pasted_text_without_selection_or_wrong_chat_is_untouched(self):
        u = update()
        u.effective_message.text = 'normal text'
        await self.admin.capture_text(u, self.context)
        self.admin.pending[42] = ('instagram', time.monotonic() + 60)
        for u in (update(user=7), update(chat=-42, kind='group')):
            await self.admin.capture_text(u, self.context)
            u.effective_message.delete.assert_not_awaited()
        self.assertEqual(self.admin.pasted, {})

    async def test_cancel_and_timeout_clear_pasted_content(self):
        u = update()
        self.admin.pending[42] = ('instagram', time.monotonic() + 60)
        self.admin.pasted[42] = ['SECRET']
        u.callback_query.data = 'cookies:cancel'
        await self.admin.callback(u, self.context)
        self.assertEqual(self.admin.pasted, {})
        self.admin.pending[42] = ('instagram', 0)
        self.admin.pasted[42] = ['SECRET']
        await self.admin.check(self.context)
        self.assertEqual(self.admin.pasted, {})

    async def test_restriction_alert_has_browser_button_and_takes_priority(self):
        self.admin.api.return_value = {'platforms': {'instagram': {
            'state': 'expired', 'version': 'v1', 'issue': 'account_restricted'}}}
        await self.admin.check(self.context)
        call = self.context.bot.send_message.call_args
        self.assertIn('account limitato', call.args[1])
        self.assertNotIn('sessione scaduti', call.args[1])
        buttons = call.kwargs['reply_markup'].inline_keyboard
        self.assertEqual(buttons[1][0].url, 'https://www.instagram.com/')

    async def test_expired_selection_and_large_file_are_not_downloaded(self):
        u = update()
        self.admin.pending[42] = ('instagram', 0)
        await self.admin.document(u, self.context)
        self.assertNotIn(42, self.admin.pending)
        self.admin.pending[42] = ('instagram', time.monotonic() + 60)
        u.effective_message.document.file_size = 1024 * 1024
        await self.admin.document(u, self.context)
        self.context.bot.get_file.assert_not_awaited()

    async def test_dedup_survives_restart(self):
        self.admin.api.return_value = {'platforms': {'instagram': {'state': 'expired', 'version': 'v1'}}}
        await self.admin.check(self.context)
        saved = dict(self.admin.alerts)
        new = CookieAdmin(AsyncMock(return_value=42), NS(get_cookie_alerts=AsyncMock(return_value=saved),
                                                        set_cookie_alerts=AsyncMock()))
        new.api = self.admin.api
        await new.check(self.context)
        self.context.bot.send_message.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
