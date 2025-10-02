async def download_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    url = msg.text.strip()
    if not is_supported_link(url):
        return
    try:
        await msg.delete()
    except:
        pass
    loading = await context.bot.send_message(msg.chat_id, "⏳ Download in corso...")
    dl = TikTokDownloader()
    try:
        info = await dl.download_video(url)
        if info['success']:
            source = (
                'TikTok' if 'tiktok' in url else
                'Instagram' if 'instagram' in url else
                'Facebook'
            )
            user_sender = msg.from_user.full_name
            title = info.get('title') or "Video scaricato da bot multi-social!"
            caption = (
                f"Video da: {source}\n"
                f"Video inviato da: {user_sender}\n"
                f"Link originale: {url}\n"
                f"{title}"
            )
            with open(info['file_path'], 'rb') as f:
                await context.bot.send_video(
                    chat_id=msg.chat_id,
                    video=f,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            await loading.delete()
            os.remove(info['file_path'])
        else:
            await loading.edit_text("❌ Contenuto non disponibile o richiede login.")
    except Exception as e:
        logger.error(f"Download error: {e}")
        err = str(e).lower()
        if 'login required' in err or 'cookie' in err:
            txt = ("❌ Impossibile scaricare: contenuto privato o limitato. "
                   "Assicurati che il post sia pubblico.")
        else:
            txt = "❌ Errore durante il download del video."
        await loading.edit_text(txt)
