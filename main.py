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
                                       "欢迎 {nickname} 加入本群！\n请先阅读群规。")
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
            # 不是字典格式，忽略（可能是其他类型事件）
            return

        # 仅处理群成员增加事件
        try:
            post_type = raw.get("post_type")
            notice_type = raw.get("notice_type")
            if post_type != "notice" or notice_type != "group_increase":
                return
        except AttributeError:
            # raw 不是字典或缺少字段，忽略
            return

        # 提取群号和用户ID
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

        # 获取新成员昵称（优先使用群名片，其次昵称，最后回退）
        nickname = self._get_nickname_from_event(event, user_id)
        message = self.welcome_message.replace("{nickname}", nickname)

        # 按分段符号拆分
        if self.segment_separator:
            segments = message.split(self.segment_separator)
        else:
            segments = [message]

        # 过滤空白段并发送
        valid_segments = [seg for seg in segments if seg.strip()]
        for seg in valid_segments:
            try:
                yield event.chain_result([Comp.Plain(text=seg)])
            except Exception as e:
                logger.error(f"发送消息段失败: {e}")
        logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len(valid_segments)} 段)")

    def _get_nickname_from_event(self, event: AstrMessageEvent, user_id: int) -> str:
        """
        尝试从事件中获取新成员昵称，回退到 "新成员(QQ号)"
        """
        # 尝试从 sender 中获取（部分协议可能在事件中携带）
        sender = getattr(event.message_obj, 'sender', None)
        if sender:
            nickname = getattr(sender, 'card', None) or getattr(sender, 'nickname', None)
            if nickname:
                return nickname
        # TODO: 未来可扩展调用 get_group_member_info API
        return f"新成员({user_id})"

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
