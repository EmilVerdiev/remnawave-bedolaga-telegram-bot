-- Обновление лендинга id=5 (slug landing): подзаголовок, фичи, футер, SEO — в духе текстов REGISTRATION_QUICK_START_PITCH
UPDATE landing_pages
SET
  title = $json$
{
  "ru": "ОБХОДЫЧ",
  "en": "Obhodich"
}
$json$::json,
  subtitle = $json$
{
  "ru": "Стабильный обход блокировок: «белые списки», глючный Telegram, YouTube, Instagram, WhatsApp — с нами снова можно пользоваться нормально. Проще «однодневок», с той поддержкой, которая реально отвечает.",
  "en": "Reliable unblocking: white lists, flaky Telegram, YouTube, Insta, WhatsApp — work again. Easier than fly-by-night services, with support that actually helps."
}
$json$::json,
  features = $json$
[
  {
    "icon": "🛡️",
    "title": {"ru": "ОБХОДЫЧ — один сервис вместо зоопарка", "en": "Obhodich — one service, not a zoo of clones"},
    "description": {"ru": "Стабильнее «однодневок», проще в настройке, с нормальной поддержкой — как в боте при регистрации.", "en": "More stable than one-day VPNs, easier setup, real support — same story as in the bot."}
  },
  {
    "icon": "🌍",
    "title": {"ru": "Работает там, где у многих уже «пусто»", "en": "Works where others can’t"},
    "description": {"ru": "В регионах РФ, где мобильный интернет душат месяцами, у конкурентов часто никого нет. У нас — стабильно.", "en": "In regions with heavy throttling, we stay available."}
  },
  {
    "icon": "🚀",
    "title": {"ru": "Скорость и низкий пинг", "en": "Speed and low ping"},
    "description": {"ru": "Телеграм и соцсети без вечного «тупняка»; YouTube в 4K — как ожидается.", "en": "Snappy social apps; YouTube in 4K as it should be."}
  },
  {
    "icon": "👻",
    "title": {"ru": "Российские приложения не паникуют", "en": "Local apps keep working"},
    "description": {"ru": "Российские сервисы нормально работают рядом с подключением — без лишнего внимания к VPN.", "en": "RU apps behave normally alongside the connection."}
  },
  {
    "icon": "📱",
    "title": {"ru": "Смартфон, ПК, Mac, Android TV", "en": "Phone, PC, Mac, TV"},
    "description": {"ru": "В подписку — несколько устройств, чтобы закрыть дом и в дороге.", "en": "Multiple devices: home and on the go."}
  },
  {
    "icon": "✅",
    "title": {"ru": "Простая настройка", "en": "Simple setup"},
    "description": {"ru": "Где достаточно «скопировать и вставить» одну ссылку — без квестов на часы.", "en": "Often just copy-paste a single link."}
  },
  {
    "icon": "💬",
    "title": {"ru": "Живая поддержка", "en": "Real support"},
    "description": {"ru": "Поможем с вопросами и сбоями — не бросаем на автоответы.", "en": "We help you through issues — not just bots."}
  },
  {
    "icon": "🤝",
    "title": {"ru": "Партнёрка", "en": "Referral program"},
    "description": {"ru": "Приведи друзей — получай бонусы, как в боте.", "en": "Refer friends for bonuses, same as in the bot."}
  }
]
$json$::json,
  footer_text = $json$
{
  "ru": "После оплаты придёт ссылка на подписку. Бот: @Obhodi4_bot · Поддержка: @obhodi4_helper",
  "en": "After payment you get a subscription link. Bot: @Obhodi4_bot · Support: @obhodi4_helper"
}
$json$::json,
  meta_title = $json$
{
  "ru": "ОБХОДЫЧ — стабильный обход блокировок",
  "en": "Obhodich — reliable unblocking"
}
$json$::json,
  meta_description = $json$
{
  "ru": "Telegram, YouTube, Instagram, WhatsApp — обход из РФ, быстрые сервера, поддержка, несколько устройств. Оформите подписку за пару кликов.",
  "en": "Unblock key apps from Russia, fast nodes, support, multiple devices. Subscribe in a few clicks."
}
$json$::json,
  updated_at = NOW()
WHERE id = 5;
