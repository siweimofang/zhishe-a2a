"""
Gotchas检索系统
===============
P0-P6完整检索链路：
  Layer 1: 领域映射（25条正则，0ms）
  Layer 2: DeepSeek LLM查询扩展（~1.2s首次，缓存后0ms）
  召回: BM25 + TF-IDF 双路
  融合: RRF (k=60)
  精排: FeatureReranker（标题/关键词/严重度/双路一致性）

用法：
  from gotchas.retriever import GotchasHybrid
  hybrid = GotchasHybrid()
  hybrid.build_index()
  results = hybrid.search("线掉下来了", top_n=5)
"""
from .tokenizer import ChineseTokenizer
from .bm25 import BM25
from .tfidf import TFIDFVector
from .reranker import FeatureReranker
from .searcher import GotchasBM25, GotchasHybrid
from .query_rewriter import QueryRewriter

__all__ = [
    'ChineseTokenizer',
    'BM25',
    'TFIDFVector', 
    'FeatureReranker',
    'GotchasBM25',
    'GotchasHybrid',
    'QueryRewriter',
]
