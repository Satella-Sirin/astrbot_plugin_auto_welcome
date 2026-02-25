from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("auto_welcome", "Satella-Sirin", "自动欢迎新成员（白名单群）", "1.0.0")
class AutoWelcomePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 设置默认配置（注意：必须用 self.context.config）
        self.context.config.set_default("group_whitelist", [])
        self.context.config.set_default("welcome_message", "欢迎 {nickname} 加入本群！")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)   # 监听所有事件
    async def on_event(self, event: AstrMessageEvent):
        # 获取原始事件数据（不同平台格式可能不同，这里以 go-cqhttp 为例）
        raw = event.message_obj.raw_message

        # 判断是否为群成员增加事件
        # go-cqhttp 格式：{"post_type":"notice","notice_type":"group_increase","group_id":123,"user_id":456}
        if hasattr(raw, 'post_type') and raw.post_type == 'notice':
            if hasattr(raw, 'notice_type') and raw.notice_type == 'group_increase':
                group_id = getattr(raw, 'group_id', None)
                user_id = getattr(raw, 'user_id', None)

                if not group_id:
                    return

                # 读取白名单配置
                whitelist = self.context.config.get("group_whitelist") or []
                if group_id not in whitelist:
                    logger.debug(f"群 {group_id} 不在白名单中，跳过")
                    return

                # 读取欢迎模板
                template = self.context.config.get("welcome_message") or "欢迎 {nickname} 加入本群！"
                # 由于无法直接获取昵称，暂时用 user_id 代替（后续可调用 API 获取）
                nickname = f"新成员({user_id})"
                message = template.replace("{nickname}", nickname)

                try:
                    await self.api.send_group_message(group_id, message)
                    logger.info(f"已向群 {group_id} 发送欢迎消息：{message}")
                except Exception as e:
                    logger.error(f"发送欢迎消息失败：{e}")

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")