from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import AstrBotConfig
import astrbot.api.message_components as Comp

@register("auto_welcome", "Satella-Sirin", "自动欢迎新成员（支持白名单群）", "1.0.0")
class AutoWelcomePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        
        # ====== 硬编码白名单群号（请在此修改您的群号）=======
        self.target_groups = {979563367, 1085866321}   # 替换成您自己的群号，多个用逗号分隔
        
        # 欢迎消息从配置读取（也可以直接写在这里）
        self.welcome_message = self.config.get("welcome_message", "新人先看群精华\n不接受可以直接退")
        
        logger.info(f"自动欢迎插件初始化: target_groups={self.target_groups}")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        # 详细调试日志：打印原始事件
        raw = event.message_obj.raw_message
        logger.info(f"on_event 收到原始事件: {raw}")

        try:
            if not isinstance(raw, dict):
                logger.debug("raw_message 不是 dict，跳过")
                return

            # 判断是否为群成员增加事件
            if raw.get("post_type") == "notice" and raw.get("notice_type") == "group_increase":
                group_id = raw.get("group_id")
                user_id = raw.get("user_id")
                logger.info(f"检测到入群事件: group_id={group_id}({type(group_id)}), user_id={user_id}")

                # 检查群号是否在白名单中
                if group_id not in self.target_groups:
                    logger.info(f"群 {group_id} 不在白名单 {self.target_groups} 中，跳过")
                    return

                # 生成欢迎消息
                nickname = f"新成员({user_id})"
                message = self.welcome_message.replace("{nickname}", nickname)
                logger.info(f"准备发送欢迎消息到群 {group_id}: {message}")

                try:
                    # ===== 分段发送：按换行符拆分成多条消息 =====
                    lines = message.split('\n')
                    for line in lines:
                        if line.strip():  # 忽略空行
                            yield event.chain_result([Comp.Plain(text=line)])
                            logger.info(f"已发送分段消息: {line}")
                    logger.info(f"已向群 {group_id} 发送欢迎消息完成")
                except Exception as e:
                    logger.error(f"发送欢迎消息失败: {e}")
            else:
                logger.debug("不是入群事件，忽略")
        except Exception as e:
            logger.error(f"处理入群事件时发生异常: {e}")

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
