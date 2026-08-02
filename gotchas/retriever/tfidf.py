"""
TF-IDF向量空间模型
余弦相似度检索，作为BM25的语义泛化补充
"""
import math
from collections import Counter


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


