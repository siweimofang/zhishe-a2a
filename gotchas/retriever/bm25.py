"""
BM25Okapi 纯Python实现
标准BM25公式: score = IDF * (tf * (k1+1)) / (tf + k1 * (1 - b + b * dl/avgdl))
"""
import math
from collections import Counter


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

