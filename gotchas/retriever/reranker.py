"""
FeatureReranker 多信号精排器
对RRF候选做二次打分：标题命中(0.40) + 关键词匹配(0.30) + 严重度(0.10) + 双路一致性(0.20)
"""


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

