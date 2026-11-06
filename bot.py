@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS: 
        return
        
    if msg.text == "/cancel":
        await state.clear()
        return await msg.answer("Рассылка отменена.")

    users = await db_get_all_users()
    if not users:
        await state.clear()
        return await msg.answer("⚠️ В базе пока нет пользователей.")

    # Отправляем статус
    status_msg = await msg.answer(f"⏳ Начинаю рассылку на {len(users)} чел...")
    success, blocked = 0, 0
    
    for uid in users:
        try:
            await msg.copy_to(chat_id=uid)
            success += 1
        except Exception as e:
            if "Forbidden" in str(e) or "blocked" in str(e): 
                blocked += 1
            else: 
                log.warning(f"Broadcast fail {uid}: {e}")
        # Пауза 0.05 сек, чтобы не словить флуд при отправке
        await asyncio.sleep(0.05)

    await state.clear()
    
    # Безопасное обновление сообщения (чтобы бот не падал при флуд-контроле)
    try:
        await status_msg.edit_text(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"Успешно доставлено: {success}\n"
            f"Заблокировали бота: {blocked}"
        )
    except Exception as e:
        log.warning(f"Не удалось обновить статус рассылки (флуд-контроль): {e}")
        # Если Telegram заблокировал редактирование, просто шлем новое сообщение
        await msg.answer(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"Успешно доставлено: {success}\n"
            f"Заблокировали бота: {blocked}"
        )
