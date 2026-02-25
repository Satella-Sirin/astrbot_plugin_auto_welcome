from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig

@register("auto_welcome", "Satella-Sirin", "自动欢迎新成员（白名单群）", "1.0.0")
class AutoWelcomePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        # 设置默认配置（如果配置文件中没有则使用默认值）
        self.config.set_default("group_whitelist", [])
        self.config.set_default("welcome_message", "欢迎 {nickname} 加入本群！")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        """监听所有事件，处理群成员增加"""
        raw = event.message_obj.raw_message

        # 判断是否为群成员增加事件（go-cqhttp 格式）
        if hasattr(raw, 'post_type') and raw.post_type == 'notice':
            if hasattr(raw, 'notice_type') and raw.notice_type == 'group_increase':
                group_id = getattr(raw, 'group_id', None)
                user_id = getattr(raw, 'user_id', None)

                if not group_id:
                    return

                # 检查白名单
                whitelist = self.config.get("group_whitelist") or []
                if group_id not in whitelist:
                    logger.debug(f"群 {group_id} 不在白名单中，跳过")
                    return

                # 获取欢迎模板
                template = self.config.get("welcome_message") or "欢迎 {nickname} 加入本群！"
                # 暂时用 user_id 代替昵称（如果需要真实昵称可额外调用 API）
                nickname = f"新成员({user_id})"
                message = template.replace("{nickname}", nickname)

                try:
                    await self.api.send_group_message(group_id, message)
                    logger.info(f"已向群 {group_id} 发送欢迎消息：{message}")
                except Exception as e:
                    logger.error(f"发送欢迎消息失败：{e}")

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
