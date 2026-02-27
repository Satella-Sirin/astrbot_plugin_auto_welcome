import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
import astrbot.api.message_components as Comp


class AutoWelcomePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self._parse_target_groups()
        self._parse_welcome_messages()
        self._parse_segment_separator()
        if not self.target_groups:
            logger.warning("当前未配置任何生效群组（target_groups 为空），插件将不会在任何群触发欢迎。")
        logger.info(f"自动欢迎插件初始化: target_groups={self.target_groups}")

    def _parse_target_groups(self):
        """解析白名单群号，转为整数集合"""
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

    def _parse_welcome_messages(self):
        """解析全局默认消息和专属消息（支持续行与空行保留）"""
        # 全局默认消息
        raw_message = self.config.get(
            "welcome_message",
            "欢迎 {at} 加入本群！\n你的昵称是 {nickname}\n---\n请先阅读群规。"
        )
        if isinstance(raw_message, str):
            self.welcome_message = raw_message.replace('\\n', '\n')
        else:
            logger.warning("welcome_message 应为字符串，已使用默认值")
            self.welcome_message = "欢迎 {at} 加入本群！\n你的昵称是 {nickname}\n---\n请先阅读群规。"

        # 专属消息（多行文本，支持续行和空行）
        raw_specials = self.config.get("welcome_messages", "")
        self.welcome_messages = {}
        if isinstance(raw_specials, str):
            lines = raw_specials.split('\n')
            merged = []
            current = None
            for line in lines:
                # 去除行尾换行符，保留左侧空格
                line = line.rstrip('\r')
                # 判断是否为新群号配置行
                if re.match(r'^\s*\d+\s*:', line):
                    if current is not None:
                        merged.append(current)
                    current = line
                else:
                    if current is not None:
                        # 续行处理：空行保留为一个换行符
                        if line == "":
                            current += '\n'
                        else:
                            current += '\n' + line
                    else:
                        # 配置以非群号开头（无效行），忽略并警告
                        if line.strip():
                            logger.warning(f"专属消息配置起始行无效，已忽略: {line}")
            if current is not None:
                merged.append(current)

            for item in merged:
                try:
                    gid_str, msg = item.split(':', 1)
                    gid_int = int(gid_str.strip())
                    # 消息内容中的 \n 转义为真实换行
                    msg = msg.strip().replace('\\n', '\n')
                    self.welcome_messages[gid_int] = msg
                except (ValueError, TypeError):
                    logger.warning(f"忽略无效的专属消息行：{item}")
        else:
            logger.warning("welcome_messages 应为字符串，已忽略")
        logger.info(f"已加载 {len(self.welcome_messages)} 条专属消息")

    def _parse_segment_separator(self):
        """解析分段符号"""
        sep = self.config.get("segment_separator", "")
        if isinstance(sep, str):
            self.segment_separator = sep
        else:
            logger.warning("segment_separator 应为字符串，已重置为空")
            self.segment_separator = ""
        if self.segment_separator:
            logger.info(f"分段符号已设置: '{self.segment_separator}'")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        raw = getattr(event.message_obj, 'raw_message', None)
        if not isinstance(raw, dict):
            return

        # 只处理群成员增加事件
        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
            return

        group_id = raw.get("group_id")
        user_id = raw.get("user_id")
        self_id = raw.get("self_id")
        if group_id is None or user_id is None or self_id is None:
            logger.debug("入群事件缺少必要字段，忽略")
            return

        # 统一转换为整数
        try:
            group_id_int = int(group_id)
            user_id_int = int(user_id)
            self_id_int = int(self_id)
        except (ValueError, TypeError) as e:
            logger.warning(
                f"群号或用户ID无法转换为整数: "
                f"group_id={group_id}, user_id={user_id}, self_id={self_id}, error={e}"
            )
            return

        # 排除机器人自身入群
        if user_id_int == self_id_int:
            logger.debug(f"机器人自身入群，跳过欢迎 (user_id={user_id_int})")
            return

        # 白名单检查
        if group_id_int not in self.target_groups:
            return

        # 获取新成员昵称并净化
        nickname = await self._fetch_member_nickname(event, group_id_int, user_id_int)
        nickname = self._escape_nickname(nickname)

        # 选择消息模板（专属 > 全局）
        message_template = self.welcome_messages.get(group_id_int, self.welcome_message)
        message = message_template.replace("{nickname}", nickname)

        # 分段发送
        if self.segment_separator:
            segments = message.split(self.segment_separator)
        else:
            segments = [message]

        valid_segments = [seg for seg in segments if seg.strip()]
        if not valid_segments:
            logger.info(f"群 {group_id_int} 的欢迎消息为空，已跳过")
            return

        for idx, seg in enumerate(valid_segments):
            chain = self._build_message_chain(seg, user_id_int)
            if chain:
                try:
                    yield event.chain_result(chain)
                except Exception as e:
                    logger.error(
                        f"发送消息段失败 (群 {group_id_int}, 段 {idx+1}/{len(valid_segments)}, "
                        f"内容: {seg[:30]}...): {e}"
                    )
        logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len(valid_segments)} 段)")

    def _escape_nickname(self, nickname: str) -> str:
        """将昵称中的 { 和 } 替换为全角字符，防止干扰占位符解析"""
        return nickname.replace('{', '｛').replace('}', '｝')

    def _build_message_chain(self, segment: str, user_id: int) -> list:
        """将可能包含 {at} 的分段文本构建为消息链"""
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

    async def _fetch_member_nickname(
        self, event: AstrMessageEvent, group_id: int, user_id: int
    ) -> str:
        """调用平台 API 获取群成员昵称（优先群名片，其次 QQ 昵称）"""
        try:
            bot = getattr(event, 'bot', None)
            if bot is not None and hasattr(bot, 'get_group_member_info'):
                member_info = await bot.get_group_member_info(
                    group_id=group_id, user_id=user_id, no_cache=True
                )
                if member_info:
                    return (
                        member_info.get('card')
                        or member_info.get('nickname')
                        or f"新成员({user_id})"
                    )
        except Exception as e:
            logger.debug(f"获取成员昵称失败 (group={group_id}, user={user_id}): {e}")
        return f"新成员({user_id})"

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
