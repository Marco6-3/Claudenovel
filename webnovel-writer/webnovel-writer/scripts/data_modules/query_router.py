#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query router for RAG requests."""
from __future__ import annotations

import re
from typing import Any, Dict, List


class QueryRouter:
    def __init__(self):
        self.intent_patterns = {
            "relationship": [
                r"关系",
                r"关系线",
                r"感情线",
                r"互动",
                r"态度",
                r"谁和谁",
                r"敌对",
                r"盟友",
                r"追求",
                r"喜欢",
                r"讨厌",
                r"边界",
                r"人设",
                r"性格",
            ],
            "entity": [
                r"人物",
                r"角色",
                r"是谁",
                r"身份",
                r"别名",
                r"状态",
                r"能力",
                r"现在",
            ],
            "scene": [
                r"地点",
                r"场景",
                r"哪里",
                r"位置",
                r"宿舍",
                r"校园",
                r"食堂",
                r"图书馆",
            ],
            "setting": [
                r"设定",
                r"规则",
                r"体系",
                r"世界观",
                r"金手指",
                r"地府",
                r"微信群",
                r"红包",
                r"道具",
            ],
            "plot": [
                r"剧情",
                r"发生",
                r"事件",
                r"经过",
                r"伏笔",
                r"线索",
                r"下一章",
                r"续写",
            ],
        }
        self.patterns = {
            "entity": list(self.intent_patterns["entity"]),
            "scene": list(self.intent_patterns["scene"]),
            "setting": list(self.intent_patterns["setting"]),
            "plot": list(self.intent_patterns["plot"]),
        }
        self.stopwords = {
            "关系",
            "关系线",
            "感情线",
            "互动",
            "态度",
            "时间线",
            "剧情",
            "发生",
            "事件",
            "经过",
            "角色",
            "人物",
            "身份",
            "状态",
            "设定",
            "规则",
            "世界观",
            "地点",
            "场景",
            "哪里",
            "位置",
            "下一章",
            "续写",
            "应该",
            "怎么",
            "为什么",
            "可以",
            "不能",
            "是否",
            "什么",
        }

    def _add_entity(self, entities: List[str], value: str) -> None:
        value = value.strip().removesuffix("的")
        value = re.sub(r"^(第?\d+(?:到|至|-|~)\d*章?|第?\d+章?)", "", value)
        value = re.sub(
            r"(的关系.*|的态度.*|的人设.*|的性格.*|关系线.*|感情线.*|关系.*|互动.*|态度.*|现在.*|应该.*|怎么.*)$",
            "",
            value,
        ).strip()
        if len(value) < 2 or value in self.stopwords or value in entities:
            return
        entities.append(value)

    def _extract_entities(self, query: str) -> List[str]:
        entities: List[str] = []
        clean = re.sub(r"第?\s*\d+\s*(?:到|至|-|~)?\s*\d*\s*章", " ", query)

        pair_patterns = [
            r"([\u4e00-\u9fff]{2,4})对([\u4e00-\u9fff]{2,4}?)(?:的)?(?:关系|关系线|感情线|互动|态度|人设|性格)",
            r"([\u4e00-\u9fff]{2,4})[和与跟同]([\u4e00-\u9fff]{2,4})(?:的)?(?:关系|关系线|感情线|互动|态度|人设|性格)",
        ]
        for pattern in pair_patterns:
            for match in re.finditer(pattern, clean):
                self._add_entity(entities, match.group(1))
                self._add_entity(entities, match.group(2))

        splitter = (
            r"对|和|与|跟|同|的|关系线|感情线|关系|互动|态度|人设|性格|"
            r"应该|怎么|延续|现在|是什么|为什么|可以|不能|是否|剧情|设定|规则"
        )
        for part in re.split(splitter, clean):
            for candidate in re.findall(r"[\u4e00-\u9fff]{2,8}", part):
                self._add_entity(entities, candidate)

        return entities[:6]

    def _extract_time_scope(self, query: str) -> Dict[str, Any]:
        m_range = re.search(r"第?\s*(\d+)\s*(?:-|~|到|至)\s*(\d+)\s*章?", query)
        if m_range:
            start = int(m_range.group(1))
            end = int(m_range.group(2))
            if start > end:
                start, end = end, start
            return {"from_chapter": start, "to_chapter": end}

        m_single = re.search(r"第?\s*(\d+)\s*章", query)
        if m_single:
            chapter = int(m_single.group(1))
            return {"from_chapter": chapter, "to_chapter": chapter}

        return {}

    def route_intent(self, query: str) -> Dict[str, Any]:
        query = str(query or "")
        intent = "plot"
        for intent_name, patterns in self.intent_patterns.items():
            if any(re.search(pattern, query) for pattern in patterns):
                intent = intent_name
                break

        time_scope = self._extract_time_scope(query)
        entities = self._extract_entities(query)
        needs_graph = (
            intent == "relationship"
            or any(term in query for term in ("关系", "关系线", "感情线", "互动", "态度", "人设", "性格"))
        )
        return {
            "intent": intent,
            "entities": entities,
            "time_scope": time_scope,
            "needs_graph": needs_graph,
            "raw_query": query,
        }

    def plan_subqueries(self, intent_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        intent = str((intent_payload or {}).get("intent") or "plot")
        entities = list((intent_payload or {}).get("entities") or [])
        time_scope = dict((intent_payload or {}).get("time_scope") or {})
        needs_graph = bool((intent_payload or {}).get("needs_graph"))

        steps: List[Dict[str, Any]] = []
        if intent == "relationship":
            steps.append(
                {
                    "name": "relationship_graph",
                    "strategy": "graph_lookup",
                    "entities": entities,
                    "time_scope": time_scope,
                }
            )
            steps.append(
                {
                    "name": "relationship_evidence",
                    "strategy": "graph_hybrid",
                    "entities": entities,
                    "time_scope": time_scope,
                }
            )
            return steps

        if needs_graph and entities:
            steps.append(
                {
                    "name": "graph_enhanced_retrieval",
                    "strategy": "graph_hybrid",
                    "entities": entities,
                    "time_scope": time_scope,
                }
            )
            return steps

        strategy_map = {
            "entity": "hybrid",
            "scene": "bm25",
            "setting": "bm25",
            "plot": "hybrid",
        }
        steps.append(
            {
                "name": "default_retrieval",
                "strategy": strategy_map.get(intent, "hybrid"),
                "entities": entities,
                "time_scope": time_scope,
            }
        )
        return steps

    def route(self, query: str) -> str:
        return str(self.route_intent(query).get("intent") or "plot")

    def split(self, query: str) -> List[str]:
        parts = re.split(r"[，,；;以及和\s]+", query)
        return [part.strip() for part in parts if part.strip()]
