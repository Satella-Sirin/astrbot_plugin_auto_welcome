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

        # 读取欢迎消息模板，处理手动输入的 \n 转义
        raw_message = self.config.get("welcome_message",
                                       "欢迎 {at} 加入本群！\n请先阅读群规。")
        self.welcome_message = raw_message.replace('\\n', '\n')

        # 读取分段符号，默认为空（不分段）
        self.segment_separator = self.config.get("segment_separator", "")
        if self.segment_separator:
            logger.info(f"分段符号已设置: '{self.segment_separator}'")

        logger.info(f"自动欢迎插件初始化: target_groups={self.target_groups}")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        # 安全获取原始消息对象
        raw = getattr(event.message_obj, 'raw_message', None)
        if not isinstance(raw, dict):
            return

        # 仅处理群成员增加事件
        try:
            post_type = raw.get("post_type")
            notice_type = raw.get("notice_type")
            if post_type != "notice" or notice_type != "group_increase":
                return
        except AttributeError:
            return

        group_id = raw.get("group_id")
        user_id = raw.get("user_id")
        if group_id is None or user_id is None:
            logger.debug("入群事件缺少 group_id 或 user_id，忽略")
            return

        # 转换群号为整数
        try:
            group_id_int = int(group_id)
        except (ValueError, TypeError):
            logger.warning(f"无法将群号 {group_id} 转换为整数，跳过")
            return

        # 白名单检查
        if group_id_int not in self.target_groups:
            return

        # 获取新成员的真实昵称（用于 {nickname} 变量）
        nickname = await self._fetch_member_nickname(event, group_id_int, user_id)
        # 先生成完整的消息文本（临时替换 nickname，但保留 {at}）
        temp_message = self.welcome_message.replace("{nickname}", nickname)

        # 按分段符号拆分
        if self.segment_separator:
            segments = temp_message.split(self.segment_separator)
        else:
            segments = [temp_message]

        # 过滤空白段并发送（每个段可能包含 {at}）
        valid_segments = [seg for seg in segments if seg.strip()]
        for seg in valid_segments:
            # 将当前段中的 {at} 替换为 at 消息段，构建消息链
            message_chain = self._build_message_chain(seg, user_id)
            if message_chain:
                try:
                    yield event.chain_result(message_chain)
                except Exception as e:
                    logger.error(f"发送消息段失败: {e}")
        logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len(valid_segments)} 段)")

    def _build_message_chain(self, segment: str, user_id: int) -> list:
        """
        将可能包含 {at} 的分段文本构建为消息链
        例如: "欢迎 {at} 加入本群！" -> [Comp.Plain("欢迎 "), Comp.At(qq=user_id), Comp.Plain(" 加入本群！")]
        """
        if "{at}" not in segment:
            # 没有 at 占位符，直接返回纯文本
            return [Comp.Plain(text=segment)]

        parts = segment.split("{at}")
        chain = []
        for i, part in enumerate(parts):
            if part:
                chain.append(Comp.Plain(text=part))
            # 在每部分之后插入 at（除了最后一部分之后）
            if i < len(parts) - 1:
                chain.append(Comp.At(qq=user_id))
        return chain

    async def _fetch_member_nickname(self, event: AstrMessageEvent, group_id: int, user_id: int) -> str:
        """调用平台 API 获取群成员昵称（优先群名片，其次 QQ 昵称）"""
        try:
            bot = getattr(event, 'bot', None)
            if bot is not None and hasattr(bot, 'get_group_member_info'):
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
