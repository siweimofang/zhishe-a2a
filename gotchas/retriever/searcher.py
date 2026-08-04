"""
Gotchas检索器（用户接口层）
- GotchasBM25: 单路BM25检索（轻量/降级用）
- GotchasHybrid: 混合检索（BM25+TF-IDF+RRF+精排+查询改写）
"""
import os
import json
import pickle

from .tokenizer import ChineseTokenizer
from .bm25 import BM25
from .tfidf import TFIDFVector
from .reranker import FeatureReranker


class GotchasBM25:
    """Gotchas知识库BM25检索器"""
    
    def __init__(self, gotchas_dir=None):
        if gotchas_dir is None:
            gotchas_dir = self._discover_gotchas_dir()
        
        self.gotchas_dir = gotchas_dir
        self.data_dir = os.path.join(gotchas_dir, 'data', 'v1.0')
        self.all_ku_file = os.path.join(self.data_dir, 'all_ku.json')
        
        # 词典路径
        dict_path = os.path.join(gotchas_dir, 'retriever', 'gotchas_dict.txt')
        self.tokenizer = ChineseTokenizer(dict_path)
        self.bm25 = BM25()
        self.all_ku = []
        self.index_built = False
    
    def _discover_gotchas_dir(self):
        """动态发现gotchas目录"""
        base = 'D:' + os.sep
        agent_dir = [d for d in os.listdir(base) if 'Agent' in d and os.path.isdir(os.path.join(base, d))][0]
        agent_path = os.path.join(base, agent_dir)
        qw_dir = [d for d in os.listdir(agent_path) if 'AI' in d and os.path.isdir(os.path.join(agent_path, d))][0]
        qw_path = os.path.join(agent_path, qw_dir)
        zs_dir = [d for d in os.listdir(qw_path) if 'zhishe' in d and os.path.isdir(os.path.join(qw_path, d))][0]
        zs_path = os.path.join(qw_path, zs_dir)
        gt_dir = [d for d in os.listdir(zs_path) if 'gotchas' in d.lower() and os.path.isdir(os.path.join(zs_path, d))][0]
        return os.path.join(zs_path, gt_dir)
    
    def load_data(self):
        """加载知识库数据"""
        with open(self.all_ku_file, 'r', encoding='utf-8') as f:
            self.all_ku = json.load(f)
        return len(self.all_ku)
    
    def build_index(self):
        """构建BM25索引"""
        if not self.all_ku:
            self.load_data()
        
        tokenized_corpus = []
        for ku in self.all_ku:
            # 索引文档 = title + keywords + scenario前200字
            title = ku.get('title', '')
            keywords = ku.get('trigger_keywords', [])
            scenario = ku.get('typical_scenario', '')[:200]
            text = f'{title} {scenario}'
            tokens = self.tokenizer.tokenize(text, keywords=keywords)
            tokenized_corpus.append(tokens)
        
        self.bm25.fit(tokenized_corpus)
        self.index_built = True
        return self.bm25.corpus_size
    
    def search(self, query, top_n=5, stage=None, trade=None, min_severity=None):
        """
        检索主函数
        
        Args:
            query: 查询文本
            top_n: 返回条数
            stage: 阶段过滤 (如 'STAGE_02')
            trade: 工种过滤 (如 'TRADE_ELECTRICAL')
            min_severity: 最低严重度 (如 'SEV_HIGH')
        
        Returns:
            list of dict: [{ku_id, title, score, stage, trade, severity, scenario, avoid}]
        """
        if not self.index_built:
            self.build_index()
        
        # 元数据预过滤
        candidate_ids = None
        if stage or trade or min_severity:
            sev_order = {'SEV_LOW': 1, 'SEV_MEDIUM': 2, 'SEV_HIGH': 3, 'SEV_CRITICAL': 4}
            candidate_ids = set()
            min_sev_val = sev_order.get(min_severity, 0) if min_severity else 0
            
            for i, ku in enumerate(self.all_ku):
                if stage and ku.get('stage') != stage:
                    continue
                if trade and trade not in ku.get('trade', []):
                    continue
                if min_severity and sev_order.get(ku.get('severity', ''), 0) < min_sev_val:
                    continue
                candidate_ids.add(i)
        
        # 分词
        query_tokens = self.tokenizer.tokenize(query)
        
        # BM25检索
        results = self.bm25.search(query_tokens, top_n=top_n, candidate_ids=candidate_ids)
        
        # 组装返回
        output = []
        for idx, score in results:
            ku = self.all_ku[idx]
            output.append({
                'ku_id': ku.get('ku_id', ''),
                'title': ku.get('title', ''),
                'score': round(score, 3),
                'stage': ku.get('stage', ''),
                'trade': ku.get('trade', []),
                'severity': ku.get('severity', ''),
                'scenario': ku.get('typical_scenario', ''),
                'avoid': ku.get('how_to_avoid', ''),
                'keywords': ku.get('trigger_keywords', [])
            })
        
        return output
    
    def save_index(self, path=None):
        """保存索引到pickle"""
        if path is None:
            path = os.path.join(self.gotchas_dir, 'retriever', 'bm25_index.pkl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump({
                'bm25': self.bm25,
                'all_ku': self.all_ku,
                'index_built': self.index_built
            }, f)
    
    def load_index(self, path=None):
        """从pickle加载索引"""
        if path is None:
            path = os.path.join(self.gotchas_dir, 'retriever', 'bm25_index.pkl')
        if not os.path.exists(path):
            return False
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.bm25 = data['bm25']
        self.all_ku = data['all_ku']
        self.index_built = data['index_built']
        return True



class GotchasHybrid:
    """Gotchas混合检索器：BM25词法 + TF-IDF语义 + RRF融合 + FeatureReranker精排"""
    
    def __init__(self, gotchas_dir=None):
        if gotchas_dir is None:
            gotchas_dir = self._discover_gotchas_dir()
        
        self.gotchas_dir = gotchas_dir
        self.data_dir = os.path.join(gotchas_dir, 'data', 'v1.0')
        self.all_ku_file = os.path.join(self.data_dir, 'all_ku.json')
        
        dict_path = os.path.join(gotchas_dir, 'retriever', 'gotchas_dict.txt')
        self.tokenizer = ChineseTokenizer(dict_path)
        self.bm25 = BM25()
        self.tfidf = TFIDFVector()
        self.reranker = FeatureReranker()
        self.rewriter = None  # P5: QueryRewriter实例（可选注入）
        self.all_ku = []
        self.tokenized_corpus = []
        self.index_built = False
    
    def enable_rewriter(self, rewriter=None):
        """启用P5查询改写（传入QueryRewriter实例，或自动创建）"""
        if rewriter is not None:
            self.rewriter = rewriter
        else:
            try:
                from gotchas.retriever.query_rewriter import QueryRewriter
                self.rewriter = QueryRewriter()
            except ImportError:
                import sys
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from query_rewriter import QueryRewriter
                self.rewriter = QueryRewriter()
        return self.rewriter.enabled
    
    def _discover_gotchas_dir(self):
        base = 'D:' + os.sep
        agent_dir = [d for d in os.listdir(base) if 'Agent' in d and os.path.isdir(os.path.join(base, d))][0]
        agent_path = os.path.join(base, agent_dir)
        qw_dir = [d for d in os.listdir(agent_path) if 'AI' in d and os.path.isdir(os.path.join(agent_path, d))][0]
        qw_path = os.path.join(agent_path, qw_dir)
        zs_dir = [d for d in os.listdir(qw_path) if 'zhishe' in d and os.path.isdir(os.path.join(qw_path, d))][0]
        zs_path = os.path.join(qw_path, zs_dir)
        gt_dir = [d for d in os.listdir(zs_path) if 'gotchas' in d.lower() and os.path.isdir(os.path.join(zs_path, d))][0]
        return os.path.join(zs_path, gt_dir)
    
    def load_data(self):
        with open(self.all_ku_file, 'r', encoding='utf-8') as f:
            self.all_ku = json.load(f)
        return len(self.all_ku)
    
    def build_index(self):
        """构建双索引（BM25 + TF-IDF）"""
        if not self.all_ku:
            self.load_data()
        
        self.tokenized_corpus = []
        for ku in self.all_ku:
            title = ku.get('title', '')
            keywords = ku.get('trigger_keywords', [])
            scenario = ku.get('typical_scenario', '')[:200]
            avoid = ku.get('how_to_avoid', '')[:150]
            text = f'{title} {scenario} {avoid}'
            tokens = self.tokenizer.tokenize(text, keywords=keywords)
            self.tokenized_corpus.append(tokens)
        
        self.bm25.fit(self.tokenized_corpus)
        self.tfidf.fit(self.tokenized_corpus)
        self.index_built = True
        return len(self.all_ku)
    
    def search(self, query, top_n=5, stage=None, trade=None, min_severity=None, rrf_k=60, use_rewriter=True):
        """
        混合检索主函数（BM25 + TF-IDF + RRF融合 + P4精排 + P5查询改写）
        
        流程：P5查询扩展(召回) → BM25+TF-IDF双路 → RRF融合 → P4精排(用原词)
        
        Args:
            query: 查询文本
            top_n: 返回条数
            stage: 阶段过滤
            trade: 工种过滤
            min_severity: 最低严重度
            rrf_k: RRF参数（默认60）
            use_rewriter: 是否启用P5查询改写（默认True）
        
        Returns:
            list of dict: [{ku_id, title, score, rank_bm25, rank_tfidf, ...}]
        """
        if not self.index_built:
            self.build_index()
        
        # 元数据预过滤
        candidate_ids = None
        if stage or trade or min_severity:
            sev_order = {'SEV_LOW': 1, 'SEV_MEDIUM': 2, 'SEV_HIGH': 3, 'SEV_CRITICAL': 4}
            candidate_ids = set()
            min_sev_val = sev_order.get(min_severity, 0) if min_severity else 0
            for i, ku in enumerate(self.all_ku):
                if stage and ku.get('stage') != stage:
                    continue
                if trade and trade not in ku.get('trade', []):
                    continue
                if min_severity and sev_order.get(ku.get('severity', ''), 0) < min_sev_val:
                    continue
                candidate_ids.add(i)
        
        # 原始分词（用于精排，保证精准度）
        original_tokens = self.tokenizer.tokenize(query)
        
        # P5+P6查询改写（用于召回，扩大覆盖面）
        # 注意：不检查rewriter.enabled，因为领域映射层(Layer 1)始终可用
        recall_tokens = original_tokens
        expanded_query = None
        if use_rewriter and self.rewriter:
            expanded_query = self.rewriter.expand(query)
            if expanded_query != query:
                recall_tokens = self.tokenizer.tokenize(expanded_query)
        
        # 双路召回（各取至少15条候选，供精排器筛选）
        recall_k = max(top_n * 3, 15)
        bm25_results = self.bm25.search(recall_tokens, top_n=recall_k, candidate_ids=candidate_ids)
        tfidf_results = self.tfidf.search(recall_tokens, top_n=recall_k, candidate_ids=candidate_ids)
        
        # RRF融合
        rrf_scores = {}
        bm25_ranks = {}
        tfidf_ranks = {}
        
        for rank, (idx, score) in enumerate(bm25_results):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
            bm25_ranks[idx] = rank + 1
        
        for rank, (idx, score) in enumerate(tfidf_results):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (rrf_k + rank + 1)
            tfidf_ranks[idx] = rank + 1
        
        # 取RRF前15候选送入精排器
        rerank_pool_size = max(top_n * 3, 15)
        fused = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:rerank_pool_size]
        
        # 构造精排输入: (idx, rrf_score, bm25_rank, tfidf_rank)
        candidates = []
        for idx, rrf_score in fused:
            candidates.append((
                idx,
                rrf_score,
                bm25_ranks.get(idx, '-'),
                tfidf_ranks.get(idx, '-')
            ))
        
        # P4精排（用原始query tokens，保证精准度）
        reranked = self.reranker.rerank(original_tokens, candidates, self.all_ku, top_n=top_n)
        
        # 组装返回
        output = []
        for idx, final_score in reranked:
            ku = self.all_ku[idx]
            output.append({
                'ku_id': ku.get('ku_id', ''),
                'title': ku.get('title', ''),
                'knowledge_type': ku.get('knowledge_type', 'gotcha'),
                'score': round(final_score, 5),
                'rank_bm25': bm25_ranks.get(idx, '-'),
                'rank_tfidf': tfidf_ranks.get(idx, '-'),
                'stage': ku.get('stage', ''),
                'trade': ku.get('trade', []),
                'severity': ku.get('severity', ''),
                'scenario': ku.get('typical_scenario', ''),
                'avoid': ku.get('how_to_avoid', ''),
                'keywords': ku.get('trigger_keywords', [])
            })
        
        return output
    
    def save_index(self, path=None):
        if path is None:
            path = os.path.join(self.gotchas_dir, 'retriever', 'hybrid_index.pkl')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump({
                'bm25': self.bm25,
                'tfidf': self.tfidf,
                'all_ku': self.all_ku,
                'tokenized_corpus': self.tokenized_corpus,
                'index_built': self.index_built
            }, f)
    
    def load_index(self, path=None):
        if path is None:
            path = os.path.join(self.gotchas_dir, 'retriever', 'hybrid_index.pkl')
        if not os.path.exists(path):
            return False
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.bm25 = data['bm25']
        self.tfidf = data['tfidf']
        self.all_ku = data['all_ku']
        self.tokenized_corpus = data['tokenized_corpus']
        self.index_built = data['index_built']
        return True
