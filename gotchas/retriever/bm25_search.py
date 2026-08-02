"""
Gotchas BM25 Retriever - 纯Python实现，零外部依赖
===================================================
功能：
  1. 中文分词（正向最大匹配 + 字符bigram + trigger_keywords）
  2. BM25Okapi 索引构建与检索
  3. 元数据过滤（stage/trade/severity）
  4. 索引持久化（pickle）

用法：
  from retriever.bm25_search import GotchasBM25
  searcher = GotchasBM25(data_dir='path/to/gotchas/data')
  searcher.build_index()
  results = searcher.search('阳台洗衣机冻裂', top_n=5)
"""

import os, json, math, pickle, re
from collections import Counter

# ============================================================
# 中文分词器（正向最大匹配 + bigram + keywords）
# ============================================================

class ChineseTokenizer:
    """基于词典的正向最大匹配分词 + 字符bigram兜底"""
    
    def __init__(self, dict_path=None):
        self.dictionary = set()
        self.max_word_len = 1
        if dict_path and os.path.exists(dict_path):
            self._load_dict(dict_path)
    
    def _load_dict(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if parts:
                    word = parts[0]
                    self.dictionary.add(word)
                    if len(word) > self.max_word_len:
                        self.max_word_len = len(word)
    
    def tokenize(self, text, keywords=None):
        """
        分词策略：
        1. trigger_keywords 直接作为token（权重最高）
        2. 正向最大匹配提取词典词（支持数字+中文混合词）
        3. 混合模式提取（数字+中文，如"50管""45度弯头""3000K"）
        4. 字符bigram兜底（捕获未登录词）
        5. 纯英文/数字token
        """
        tokens = []
        
        # 1. keywords 直接加入（重复2次增加权重）
        if keywords:
            for kw in keywords:
                tokens.append(kw)
                tokens.append(kw)
        
        # 2. 正向最大匹配（从每个位置尝试，包括数字开头）
        fmm_tokens = self._fmm(text)
        tokens.extend(fmm_tokens)
        
        # 3. 混合模式提取：数字+中文、数字+字母+中文
        #    匹配 "50管" "45度弯头" "3000K" "850mm" "2.5平方线"
        mixed_patterns = re.findall(r'[0-9]+[.]?[0-9]*[\u4e00-\u9fffA-Za-z]+[0-9\u4e00-\u9fffA-Za-z]*', text)
        for mp in mixed_patterns:
            tokens.append(mp)
            tokens.append(mp)  # 加权
        
        # 4. 字符bigram（仅对中文部分）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        for i in range(len(chinese_chars) - 1):
            tokens.append(chinese_chars[i] + chinese_chars[i+1])
        
        # 5. 纯英文/数字token
        alpha_tokens = re.findall(r'[a-zA-Z]+|[0-9]+', text)
        tokens.extend([t.lower() for t in alpha_tokens])
        
        return tokens
    
    def _fmm(self, text):
        """正向最大匹配（支持数字/字母开头的混合词）"""
        tokens = []
        i = 0
        while i < len(text):
            # 跳过纯空白和标点
            ch = text[i]
            if ch in ' \t\n\r，。！？、；：""''（）【】《》…—·,.:;!?()[]{}':
                i += 1
                continue
            
            matched = False
            max_len = min(self.max_word_len, len(text) - i)
            for length in range(max_len, 1, -1):
                candidate = text[i:i+length]
                if candidate in self.dictionary:
                    tokens.append(candidate)
                    i += length
                    matched = True
                    break
            
            if not matched:
                i += 1
        
        return tokens


# ============================================================
# BM25Okapi 实现
# ============================================================

class BM25:
    """BM25Okapi 纯Python实现"""
    
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0
        self.doc_freqs = {}      # term -> 包含该term的文档数
        self.doc_lens = []       # 每个文档的长度
        self.tf = []             # 每个文档的 term frequency dict
        self.idf = {}            # term -> IDF值
    
    def fit(self, tokenized_corpus):
        """构建索引"""
        self.corpus_size = len(tokenized_corpus)
        self.doc_lens = [len(doc) for doc in tokenized_corpus]
        self.avgdl = sum(self.doc_lens) / self.corpus_size if self.corpus_size > 0 else 1
        
        self.tf = []
        self.doc_freqs = {}
        
        for doc in tokenized_corpus:
            tf = Counter(doc)
            self.tf.append(tf)
            for term in set(doc):
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1
        
        # 计算IDF
        self.idf = {}
        for term, df in self.doc_freqs.items():
            # 标准BM25 IDF公式
            self.idf[term] = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1)
    
    def score(self, query_tokens, doc_idx):
        """计算单个文档对查询的BM25分数"""
        score = 0.0
        doc_len = self.doc_lens[doc_idx]
        tf_dict = self.tf[doc_idx]
        
        for term in query_tokens:
            if term not in tf_dict:
                continue
            tf = tf_dict[term]
            idf = self.idf.get(term, 0)
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
            score += idf * numerator / denominator
        
        return score
    
    def search(self, query_tokens, top_n=10, candidate_ids=None):
        """检索Top-N"""
        scores = []
        for i in range(self.corpus_size):
            if candidate_ids is not None and i not in candidate_ids:
                continue
            s = self.score(query_tokens, i)
            if s > 0:
                scores.append((i, s))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]


# ============================================================
# Gotchas BM25 检索器（主类）
# ============================================================

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


# ============================================================
# TF-IDF 向量检索（语义泛化补充）
# ============================================================

class TFIDFVector:
    """TF-IDF向量空间模型，提供语义级相似度检索"""
    
    def __init__(self):
        self.vocab = {}          # term -> index
        self.idf = {}            # term -> IDF值
        self.doc_vectors = []    # 每个文档的TF-IDF稀疏向量 (dict: term_idx -> weight)
        self.doc_norms = []      # 每个文档向量的L2范数
        self.corpus_size = 0
    
    def fit(self, tokenized_corpus):
        """构建TF-IDF向量索引"""
        self.corpus_size = len(tokenized_corpus)
        
        # 计算DF
        df = {}
        for doc in tokenized_corpus:
            for term in set(doc):
                df[term] = df.get(term, 0) + 1
        
        # 构建词汇表和IDF
        self.vocab = {term: i for i, term in enumerate(sorted(df.keys()))}
        self.idf = {term: math.log((self.corpus_size + 1) / (freq + 1)) + 1 
                    for term, freq in df.items()}
        
        # 计算每个文档的TF-IDF向量
        self.doc_vectors = []
        self.doc_norms = []
        
        for doc in tokenized_corpus:
            tf = Counter(doc)
            doc_len = len(doc)
            vec = {}
            norm_sq = 0.0
            
            for term, count in tf.items():
                if term not in self.vocab:
                    continue
                # TF: 对数归一化
                tf_weight = 1 + math.log(count) if count > 0 else 0
                # TF-IDF
                weight = tf_weight * self.idf.get(term, 1.0)
                idx = self.vocab[term]
                vec[idx] = weight
                norm_sq += weight * weight
            
            self.doc_vectors.append(vec)
            self.doc_norms.append(math.sqrt(norm_sq) if norm_sq > 0 else 1.0)
    
    def search(self, query_tokens, top_n=10, candidate_ids=None):
        """余弦相似度检索"""
        # 构建查询向量
        tf = Counter(query_tokens)
        q_vec = {}
        q_norm_sq = 0.0
        
        for term, count in tf.items():
            if term not in self.vocab:
                continue
            tf_weight = 1 + math.log(count) if count > 0 else 0
            weight = tf_weight * self.idf.get(term, 1.0)
            idx = self.vocab[term]
            q_vec[idx] = weight
            q_norm_sq += weight * weight
        
        q_norm = math.sqrt(q_norm_sq) if q_norm_sq > 0 else 1.0
        
        # 计算与每个文档的余弦相似度
        scores = []
        for i in range(self.corpus_size):
            if candidate_ids is not None and i not in candidate_ids:
                continue
            
            # 稀疏向量点积
            dot = 0.0
            doc_vec = self.doc_vectors[i]
            for idx, w in q_vec.items():
                if idx in doc_vec:
                    dot += w * doc_vec[idx]
            
            if dot > 0:
                cosine = dot / (q_norm * self.doc_norms[i])
                scores.append((i, cosine))
        
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]


# ============================================================
# 特征精排器（P4: 替代 Cross-Encoder 的轻量重排序）
# ============================================================

class FeatureReranker:
    """
    多特征精排器：对RRF候选做二次打分
    信号权重：
      - title_overlap: 查询词在标题中的命中率（最强信号）
      - keyword_match: 查询词与trigger_keywords的匹配度
      - severity_boost: 严重度加权（CRITICAL > HIGH > MEDIUM > LOW）
      - dual_rank: 双路排名一致性（BM25和TF-IDF都靠前 = 更可信）
    """
    
    SEVERITY_WEIGHTS = {
        'SEV_CRITICAL': 1.3,
        'SEV_HIGH': 1.15,
        'SEV_MEDIUM': 1.0,
        'SEV_LOW': 0.9
    }
    
    def __init__(self, w_title=0.40, w_keyword=0.30, w_severity=0.10, w_dual=0.20):
        self.w_title = w_title
        self.w_keyword = w_keyword
        self.w_severity = w_severity
        self.w_dual = w_dual
    
    def rerank(self, query_tokens, candidates, all_ku, top_n=5):
        """
        对候选列表精排
        
        Args:
            query_tokens: 分词后的查询token列表
            candidates: RRF融合后的候选 [(idx, rrf_score, bm25_rank, tfidf_rank)]
            all_ku: 全量KU数据
            top_n: 返回条数
        
        Returns:
            精排后的 [(idx, final_score)] 列表
        """
        if not candidates:
            return []
        
        # 提取查询中的有意义token（去重，长度>=2）
        q_terms = set(t for t in query_tokens if len(t) >= 2)
        if not q_terms:
            q_terms = set(query_tokens)
        
        scored = []
        for idx, rrf_score, bm25_rank, tfidf_rank in candidates:
            ku = all_ku[idx]
            
            # 1. 标题命中率
            title = ku.get('title', '')
            title_hits = sum(1 for t in q_terms if t in title)
            title_score = title_hits / len(q_terms) if q_terms else 0
            
            # 2. 关键词匹配率
            keywords = ku.get('trigger_keywords', [])
            kw_text = ' '.join(keywords)
            kw_hits = sum(1 for t in q_terms if t in kw_text)
            kw_score = kw_hits / len(q_terms) if q_terms else 0
            
            # 3. 严重度加权
            sev = ku.get('severity', 'SEV_MEDIUM')
            sev_weight = self.SEVERITY_WEIGHTS.get(sev, 1.0)
            
            # 4. 双路一致性（两路都排前5 = 高分）
            dual_score = 0.0
            if bm25_rank != '-' and tfidf_rank != '-':
                # 两路都命中，按平均排名打分
                avg_rank = (bm25_rank + tfidf_rank) / 2
                dual_score = 1.0 / (1 + avg_rank * 0.2)
            elif bm25_rank != '-' or tfidf_rank != '-':
                # 只有一路命中
                r = bm25_rank if bm25_rank != '-' else tfidf_rank
                dual_score = 0.5 / (1 + r * 0.2)
            
            # 综合打分
            final = (
                self.w_title * title_score +
                self.w_keyword * kw_score +
                self.w_severity * (sev_weight - 0.9) / 0.4 +  # 归一化到0-1
                self.w_dual * dual_score
            )
            
            # RRF分数作为基础分（微调）
            final += rrf_score * 0.5
            
            scored.append((idx, final))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]


# ============================================================
# 混合检索器（BM25 + TF-IDF + RRF 融合 + 精排）
# ============================================================

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
