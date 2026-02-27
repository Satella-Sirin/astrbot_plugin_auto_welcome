import json
from pathlib import Path
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.core.star.star_tools import StarTools

# 注意：本插件基于 OneBot 协议（aiocqhttp）开发，仅支持该平台。
class AutoWelcomePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        # 配置使用标准数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_auto_welcome")
        self.config_file = self.data_dir / "config.json"
        self._load_config()

    def _load_config(self):
        """从数据目录加载配置文件"""
        default_config = {
            "target_groups": [],
            "welcome_message": "欢迎 {nickname} 加入本群！\n请先阅读群规。",
            "segment_separator": ""
        }
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 合并默认值，确保所有字段都存在
                self.config = {**default_config, **loaded}
            except Exception as e:
                logger.error(f"读取配置文件失败，使用默认配置: {e}")
                self.config = default_config
        else:
            self.config = default_config
            self._save_config()  # 保存默认配置

        # 解析白名单群号
        raw_groups = self.config.get("target_groups", [])
        if not isinstance(raw_groups, list):
            logger.warning("配置项 target_groups 应为列表，已重置为空")
            raw_groups = []
        self.target_groups = set()
        for g in raw_groups:
            try:
                self.target_groups.add(int(g))
            except (ValueError, TypeError):
                logger.warning(f"配置中的群号 {g} 无法转为整数，已忽略")

        # 处理欢迎消息中的转义
        raw_message = self.config.get("welcome_message", default_config["welcome_message"])
        self.welcome_message = raw_message.replace('\\n', '\n')

        self.segment_separator = self.config.get("segment_separator", "")

        logger.info(f"自动欢迎插件初始化: target_groups={self.target_groups}")

    def _save_config(self):
        """保存配置到文件"""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    async def initialize(self):
        logger.info("自动欢迎插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        # 极速过滤：仅处理可能是通知的事件
        raw = getattr(event.message_obj, 'raw_message', None)
        if not isinstance(raw, dict):
            return

        # 检查是否为入群通知（OneBot 特有字段）
        if raw.get("post_type") != "notice" or raw.get("notice_type") != "group_increase":
            return

        group_id = raw.get("group_id")
        user_id = raw.get("user_id")
        if group_id is None or user_id is None:
            return

        # 转换群号为整数
        try:
            group_id_int = int(group_id)
        except (ValueError, TypeError):
            logger.warning(f"无法将群号 {group_id} 转换为整数，跳过")
            return

        if group_id_int not in self.target_groups:
            return

        # 获取新成员昵称（主动调用 API）
        nickname = await self._fetch_member_nickname(event, group_id_int, user_id)

        message = self.welcome_message.replace("{nickname}", nickname)

        # 分段发送
        if self.segment_separator:
            segments = message.split(self.segment_separator)
        else:
            segments = [message]

        valid_segments = [seg for seg in segments if seg.strip()]
        for seg in valid_segments:
            # 注意：此处 yield 只是将消息链交给框架，无法捕获网络发送异常
            yield event.chain_result([Comp.Plain(text=seg)])

        logger.info(f"已向群 {group_id_int} 发送欢迎消息 (共 {len(valid_segments)} 段)")

    async def _fetch_member_nickname(self, event: AstrMessageEvent, group_id: int, user_id: int) -> str:
        """调用平台 API 获取群成员昵称（优先群名片）"""
        try:
            # 尝试获取 bot 实例（仅支持 OneBot 协议）
            bot = getattr(event, 'bot', None)
            if bot is not None and hasattr(bot, 'get_group_member_info'):
                member_info = await bot.get_group_member_info(
                    group_id=group_id,
                    user_id=user_id,
                    no_cache=True
                )
                if member_info:
                    # 返回群名片（card）或昵称（nickname）
                    return member_info.get('card') or member_info.get('nickname') or f"新成员({user_id})"
        except Exception as e:
            logger.debug(f"获取成员昵称失败: {e}")
        return f"新成员({user_id})"

    async def terminate(self):
        logger.info("自动欢迎插件已卸载")
