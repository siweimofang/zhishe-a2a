"""
Gotchas中文分词器
正向最大匹配(FMM) + 字符bigram + 混合模式(数字+中文) + trigger_keywords加权
零外部依赖
"""
import os
import re


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

