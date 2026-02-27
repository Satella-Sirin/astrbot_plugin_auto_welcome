import asyncio
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
from astrbot.core import AstrBotConfig
import astrbot.api.message_components as Comp

class AutoWelcomePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        
        # 从配置读取白名单群号，统一转换为整数集合
        raw_groups = self.config.get("target_groups", [])
        self.target_groups = set()
        for g in raw_groups:
            try:
                self.target_groups.add(int(g))
            except (ValueError, TypeError):
                logger.warning(f"配置中的群号 {g} 无法转为整数，已忽略")
        
        # 从配置读取欢迎消息，并处理可能误输入的字面 \n
        raw_message = self.config.get("welcome_message", "新人先看群精华\n不接受可以直接退")
        self.welcome_message = raw_message.replace('\\n', '\n')
        
        logger.info(f"自动欢迎插件初始化: target_groups={self.target_groups}")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        raw = event.message_obj.raw_message
        # 调试时可取消下一行的注释
        # logger.info(f"on_event 收到原始事件: {raw}")

        try:
            if not isinstance(raw, dict):
                return

            # 判断是否为群成员增加事件
            if raw.get("post_type") == "notice" and raw.get("notice_type") == "group_increase":
                group_id = raw.get("group_id")
                user_id = raw.get("user_id")
                # 调试时可保留下面这行，确认入群事件触发
                # logger.info(f"检测到入群事件: group_id={group_id}, user_id={user_id}")

                # 将 group_id 转换为整数进行白名单检查
                try:
                    group_id_int = int(group_id)
                except (ValueError, TypeError):
                    logger.error(f"无法将群号 {group_id} 转换为整数，跳过")
                    return

                if group_id_int not in self.target_groups:
                    # 白名单不匹配时，如果需要调试可取消下面注释
                    # logger.info(f"群 {group_id_int} 不在白名单 {self.target_groups} 中，跳过")
                    return

                nickname = f"新成员({user_id})"
                message = self.welcome_message.replace("{nickname}", nickname)

                # 分段发送
                lines = message.split('\n')
                for line in lines:
                    if line.strip():
                        yield event.chain_result([Comp.Plain(text=line)])
                logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len([l for l in lines if l.strip()])} 段)")
        except Exception as e:
            logger.error(f"处理入群事件异常: {e}")

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
