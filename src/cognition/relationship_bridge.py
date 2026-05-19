"""
relationship_bridge.py
关系桥接模块 - 自动读取本地其他人设，生成关系上下文

仅在特定人设（如劳伦缇娜）激活时触发。
读取 personas/ 目录下的其他人设文件，提取关键信息，
通过 LLM 生成自然的关系描述，注入到当前人设的 system prompt 中。
"""
import yaml
import json
import asyncio
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class PersonaBrief:
    """其他人设的简要信息"""
    name: str
    description: str
    personality: str
    background: str
    knowledge_scope: str
    opinions_summary: str


@dataclass
class RelationshipContext:
    """生成的关系上下文"""
    persona_name: str
    related_persona: str
    relationship_text: str


class RelationshipBridge:
    """
    关系桥接器
    
    当特定人设（如劳伦缇娜）激活时：
    1. 扫描 personas/ 目录下的其他人设文件
    2. 提取每个人设的关键信息（姓名、性格、背景、爱好、观点）
    3. 调用 LLM 生成当前人设对其他人设的关系认知
    4. 将关系认知注入到 system prompt 中
    """

    # 需要启用关系桥接的人设列表
    BRIDGE_ENABLED_PERSONAS = {"Laurentina", "劳伦缇娜"}
    
    # 关系缓存文件路径
    CACHE_DIR = "data"
    CACHE_FILE = "relationship_cache.json"

    def __init__(self, personas_dir: str = "personas", llm_client=None):
        self.personas_dir = Path(personas_dir)
        self.llm_client = llm_client
        self._cache = {}
        self._load_cache()

    def _load_cache(self):
        """加载关系缓存"""
        cache_path = Path(self.CACHE_DIR) / self.CACHE_FILE
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}

    def _save_cache(self):
        """保存关系缓存"""
        cache_path = Path(self.CACHE_DIR) / self.CACHE_FILE
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def should_activate(self, persona_name: str) -> bool:
        """判断是否需要激活关系桥接"""
        return persona_name in self.BRIDGE_ENABLED_PERSONAS

    def _extract_persona_brief(self, persona_name: str) -> PersonaBrief | None:
        """从 YAML 文件中提取人设简要信息"""
        # 尝试多种文件名格式
        candidates = [
            self.personas_dir / f"{persona_name}.yaml",
            self.personas_dir / f"{persona_name}.yml",
        ]
        
        # 也搜索目录下所有 yaml 文件，按名称匹配
        if self.personas_dir.exists():
            for f in self.personas_dir.glob("*.yaml"):
                if f.stem.lower() == persona_name.lower():
                    candidates.insert(0, f)
                    break
        
        for path in candidates:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = yaml.safe_load(f)
                    
                    identity = raw.get("identity", {})
                    knowledge = raw.get("knowledge", {})
                    opinions = knowledge.get("opinions", [])
                    
                    opinions_text = "\n".join(
                        f"- {op.get('topic', '')}: {op.get('stance', '')}"
                        for op in opinions
                    )
                    
                    return PersonaBrief(
                        name=raw.get("name", persona_name),
                        description=identity.get("description", ""),
                        personality=identity.get("personality", ""),
                        background=identity.get("background", ""),
                        knowledge_scope=knowledge.get("scope", ""),
                        opinions_summary=opinions_text,
                    )
                except Exception:
                    continue
        return None

    def _get_all_other_personas(self, current_persona: str) -> list[PersonaBrief]:
        """获取除当前人设外的所有其他人设简要信息"""
        others = []
        if not self.personas_dir.exists():
            return others
        
        for path in self.personas_dir.glob("*.yaml"):
            name = path.stem
            # 跳过当前人设
            if name == current_persona:
                continue
            brief = self._extract_persona_brief(name)
            if brief:
                others.append(brief)
        
        return others

    async def generate_relationship(
        self, 
        current_persona: str, 
        current_persona_file: str,
        llm_client=None
    ) -> str:
        """
        生成当前人设对其他人设的关系认知
        
        Returns:
            格式化的关系上下文字符串，可直接注入 system prompt
        """
        if not self.should_activate(current_persona):
            return ""

        # 检查缓存
        cache_key = current_persona
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            # 缓存有效期：人设文件修改时间
            persona_path = Path(current_persona_file)
            if persona_path.exists():
                mtime = persona_path.stat().st_mtime
                if cached.get("mtime") == mtime:
                    return cached.get("relationship_text", "")

        # 获取其他人设信息
        others = self._get_all_other_personas(current_persona)
        if not others:
            return ""

        # 获取当前人设信息
        current_brief = self._extract_persona_brief(
            Path(current_persona_file).stem
        )
        if not current_brief:
            return ""

        # 使用 LLM 生成关系描述
        client = llm_client or self.llm_client
        if not client:
            # 没有 LLM 客户时，生成基础关系文本
            return self._generate_basic_relationship(current_brief, others)

        try:
            relationship_text = await self._call_llm_for_relationship(
                current_brief, others, client
            )
            
            # 缓存结果
            persona_path = Path(current_persona_file)
            self._cache[cache_key] = {
                "mtime": persona_path.stat().st_mtime if persona_path.exists() else 0,
                "relationship_text": relationship_text,
            }
            self._save_cache()
            
            return relationship_text
        except Exception as e:
            # LLM 调用失败时使用基础版本
            return self._generate_basic_relationship(current_brief, others)

    def _generate_basic_relationship(
        self, current: PersonaBrief, others: list[PersonaBrief]
    ) -> str:
        """生成基础版关系描述（不依赖 LLM）"""
        lines = []
        lines.append("【社交关系认知】")
        lines.append(f"以下是{current.name}认识的人：")
        lines.append("")
        
        for other in others:
            lines.append(f"【{other.name}】")
            if other.description:
                # 提取第一句作为简介
                first_line = other.description.strip().split("\n")[0].strip()
                lines.append(f"  身份：{first_line}")
            if other.personality:
                # 提取关键性格特征
                personality_lines = [
                    l.strip() for l in other.personality.strip().split("\n") 
                    if l.strip()
                ]
                if personality_lines:
                    lines.append(f"  性格：{personality_lines[0]}")
            lines.append("")
        
        return "\n".join(lines)

    async def _call_llm_for_relationship(
        self,
        current: PersonaBrief,
        others: list[PersonaBrief],
        client
    ) -> str:
        """调用 LLM 生成自然的关系描述"""
        
        others_text = ""
        for other in others:
            others_text += f"\n--- {other.name} ---\n"
            others_text += f"身份：{other.description}\n"
            others_text += f"性格：{other.personality}\n"
            others_text += f"背景：{other.background}\n"
            others_text += f"兴趣范围：{other.knowledge_scope}\n"
            others_text += f"观点：\n{other.opinions_summary}\n"

        prompt = f"""你是一个关系分析师。请根据以下两个人设的信息，生成{current.name}对其他人设的关系认知。

当前人设：{current.name}
身份：{current.description}
性格：{current.personality}
背景：{current.background}

认识的人：
{others_text}

请生成{current.name}对每个人的自然关系认知，要求：
1. 用{current.name}的第一人称视角，以她说话的风格描述关系
2. 包含：怎么认识的、对对方的印象、关系亲疏、互动方式
3. 语气要自然，像在跟朋友提起"我认识的一个人"
4. 不要太长，每个人2-4句话
5. 要体现{current.name}的性格特点（直接、慵懒、有审美标准）
6. 如果有多个认识的人，分别描述

输出格式：
【关系认知】
（直接输出关系描述，不要加额外说明）"""

        try:
            # 尝试使用 LLM 客户端
            if hasattr(client, 'chat'):
                # OpenAI 风格的客户端
                response = await client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1000,
                    temperature=0.7,
                )
                if hasattr(response, 'choices'):
                    return response.choices[0].message.content
                elif isinstance(response, dict):
                    return response.get('choices', [{}])[0].get('message', {}).get('content', '')
            elif hasattr(client, 'generate'):
                return await client.generate(prompt)
            elif callable(client):
                return await client(prompt)
        except Exception as e:
            raise e
        
        return self._generate_basic_relationship(current, others)

    def clear_cache(self, persona_name: str = None):
        """清除关系缓存"""
        if persona_name:
            self._cache.pop(persona_name, None)
        else:
            self._cache = {}
        self._save_cache()


# 全局实例
_bridge_instance = None

def get_relationship_bridge(personas_dir: str = "personas", llm_client=None) -> RelationshipBridge:
    """获取关系桥接器的全局实例"""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = RelationshipBridge(personas_dir, llm_client)
    return _bridge_instance
