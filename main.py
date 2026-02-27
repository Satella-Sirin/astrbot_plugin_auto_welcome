from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
import astrbot.api.message_components as Comp

class AutoWelcomePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}

        # 校验 target_groups 是否为列表
        raw_groups = self.config.get("target_groups", [])
        if not isinstance(raw_groups, (list, tuple, set)):
            logger.warning(f"配置项 target_groups 应为列表，实际为 {type(raw_groups)}，已忽略")
            raw_groups = []
        self.target_groups = set()
        for g in raw_groups:
            try:
                self.target_groups.add(int(g))
            except (ValueError, TypeError):
                logger.warning(f"配置中的群号 {g} 无法转为整数，已忽略")

        # 读取全局默认欢迎消息，并确保是字符串
        raw_message = self.config.get("welcome_message",
                                       "欢迎 {at} 加入本群！\n你的昵称是 {nickname}\n---\n请先阅读群规。")
        if not isinstance(raw_message, str):
            logger.warning(f"welcome_message 应为字符串，实际为 {type(raw_message)}，使用默认值")
            raw_message = "欢迎 {at} 加入本群！\n你的昵称是 {nickname}\n---\n请先阅读群规。"
        self.welcome_message = raw_message.replace('\\n', '\n')

        # 解析专属欢迎消息（多行文本格式：群号:消息），并确保是字符串
        raw_welcome_messages = self.config.get("welcome_messages", "")
        if not isinstance(raw_welcome_messages, str):
            logger.warning(f"welcome_messages 应为字符串，实际为 {type(raw_welcome_messages)}，已忽略")
            raw_welcome_messages = ""
        self.welcome_messages = {}
        if raw_welcome_messages:
            for line in raw_welcome_messages.split('\n'):
                line = line.strip()
                if not line or ':' not in line:
                    continue
                try:
                    gid_str, msg = line.split(':', 1)
                    gid_int = int(gid_str.strip())
                    msg = msg.strip().replace('\\n', '\n')
                    self.welcome_messages[gid_int] = msg
                except (ValueError, TypeError):
                    logger.warning(f"忽略无效的专属消息行：{line}")
        logger.info(f"已加载 {len(self.welcome_messages)} 条专属消息")

        # 读取分段符号，确保是字符串
        raw_sep = self.config.get("segment_separator", "")
        if not isinstance(raw_sep, str):
            logger.warning(f"segment_separator 应为字符串，实际为 {type(raw_sep)}，已重置为空")
            raw_sep = ""
        self.segment_separator = raw_sep
        if self.segment_separator:
            logger.info(f"分段符号已设置: '{self.segment_separator}'")

        logger.info(f"自动欢迎插件初始化: target_groups={self.target_groups}")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        raw = getattr(event.message_obj, 'raw_message', None)
        if not isinstance(raw, dict):
            return
        # 快速过滤非目标事件
        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
            return

        group_id = raw.get("group_id")
        user_id = raw.get("user_id")
        if group_id is None or user_id is None:
            logger.debug("入群事件缺少 group_id 或 user_id，忽略")
            return

        # 转换群号和用户ID为整数
        try:
            group_id_int = int(group_id)
            user_id_int = int(user_id)
        except (ValueError, TypeError):
            logger.warning(f"无法将群号 {group_id} 或用户ID {user_id} 转换为整数，跳过")
            return

        if group_id_int not in self.target_groups:
            return

        nickname = await self._fetch_member_nickname(event, group_id_int, user_id_int)

        # 选择消息模板
        message_template = self.welcome_messages.get(group_id_int, self.welcome_message)
        message = message_template.replace("{nickname}", nickname)

        # 分段
        if self.segment_separator:
            segments = message.split(self.segment_separator)
        else:
            segments = [message]

        valid_segments = [seg for seg in segments if seg.strip()]
        if not valid_segments:
            logger.info(f"群 {group_id_int} 欢迎消息为空，已跳过")
            return

        for seg in valid_segments:
            chain = self._build_message_chain(seg, user_id_int)
            if chain:
                try:
                    yield event.chain_result(chain)
                except Exception as e:
                    logger.error(f"发送消息段失败: {e}")
        logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len(valid_segments)} 段)")

    def _build_message_chain(self, segment: str, user_id: int) -> list:
        if "{at}" not in segment:
            return [Comp.Plain(text=segment)]
        parts = segment.split("{at}")
        chain = []
        for i, part in enumerate(parts):
            if part:
                chain.append(Comp.Plain(text=part))
            if i < len(parts) - 1:
                chain.append(Comp.At(qq=user_id))
        return chain

    async def _fetch_member_nickname(self, event: AstrMessageEvent, group_id: int, user_id: int) -> str:
        try:
            bot = getattr(event, 'bot', None)
            if bot and hasattr(bot, 'get_group_member_info'):
                member_info = await bot.get_group_member_info(
                    group_id=group_id,
                    user_id=user_id,
                    no_cache=True
                )
                if member_info:
                    return member_info.get('card') or member_info.get('nickname') or f"新成员({user_id})"
        except Exception as e:
            logger.debug(f"获取成员昵称失败: {e}")
        return f"新成员({user_id})"

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
