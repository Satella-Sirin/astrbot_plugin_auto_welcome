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
        
        # 读取欢迎消息模板
        raw_message = self.config.get("welcome_message", "新人先看群精华\n不接受可以直接退")
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
        try:
            raw = event.message_obj.raw_message
            if not isinstance(raw, dict):
                return

            if raw.get("post_type") == "notice" and raw.get("notice_type") == "group_increase":
                group_id = raw.get("group_id")
                user_id = raw.get("user_id")

                try:
                    group_id_int = int(group_id)
                except (ValueError, TypeError):
                    logger.exception(f"无法将群号 {group_id} 转换为整数")
                    return

                if group_id_int not in self.target_groups:
                    return

                nickname = f"新成员({user_id})"
                message = self.welcome_message.replace("{nickname}", nickname)

                # 根据分段符号拆分消息
                if self.segment_separator:
                    segments = message.split(self.segment_separator)
                else:
                    segments = [message]

                # 过滤掉完全空白的分段（但保留可能包含换行的非空内容）
                valid_segments = [seg for seg in segments if seg.strip()]
                
                for seg in valid_segments:
                    yield event.chain_result([Comp.Plain(text=seg)])
                
                logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len(valid_segments)} 段)")
        except Exception:
            logger.exception("处理入群事件时发生未预期异常")

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
