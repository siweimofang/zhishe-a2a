"""
P5+P6: LLM查询改写器 + 领域映射层（DeepSeek）
解决词汇鸿沟：用户口语 → 知识库专业术语

双层扩展架构：
  Layer 1 - 领域映射（DOMAIN_MAPPINGS）：正则模式匹配，零延迟，确定性
  Layer 2 - LLM扩展（DeepSeek API）：广覆盖，处理未见过的表达

设计原则：
  - 召回阶段用扩展词（宽进）
  - 精排阶段用原始词（严出）
  - API失败时静默降级，领域映射层始终可用
  - LRU缓存避免重复API调用
"""
import os
import re
import json
import time
import urllib.request
import urllib.error
from collections import OrderedDict


class QueryRewriter:
    """
    双层查询改写器：领域映射 + DeepSeek LLM
    
    Layer 1（领域映射）：装修老师傅的口语→术语对应关系，确定性、零延迟
    Layer 2（LLM扩展）：DeepSeek通用语义扩展，覆盖未见过的表达
    
    示例：
      "线掉下来了" → 领域映射命中 → +50管/电视墙/线路外露 → LLM补充 → +电线脱落/线槽
      "臭味" → 领域映射命中 → +异味/通风/鞋柜 → LLM补充 → +甲醛/板材/除味
    """
    
    # ================================================================
    # Layer 1: 领域映射表（装修口语 → 专业术语）
    # 格式：(正则模式, 注入术语列表)
    # 这是Gotchas库的核心资产——沉淀行业know-how
    # ================================================================
    DOMAIN_MAPPINGS = [
        # --- 线路/电线 ---
        (r'线.{0,3}(掉|落|垂|露|外露|耷拉|脱)', 
         '50管 电视墙预埋 线路外露 穿线管 PVC管 暗埋 电视墙 走线'),
        (r'(电线|线缆|线管).{0,3}(掉|落|垂|露|松)', 
         '50管 电视墙 预埋管 走线 暗装 线槽'),
        (r'(电视|壁挂|挂墙).{0,3}(线|管|露)', 
         '50管 电视墙预埋 线路外露 HDMI 穿线管'),
        
        # --- 马桶/下水堵塞 ---
        (r'(马桶|坐便|便池).{0,3}(堵|塞|不通|排水慢|反味)', 
         '下水管 90度弯头 45度弯头 排水坡度 管道堵塞 存水弯 坑距'),
        (r'(堵|塞|不通|反水).{0,3}(马桶|下水|排水|地漏)', 
         '下水管 弯头 排水坡度 管道疏通 存水弯 地漏'),
        (r'(下水|排水).{0,3}(慢|堵|反|臭)', 
         '下水管 弯头 排水坡度 存水弯 地漏 通气帽'),
        
        # --- 臭味/异味 ---
        (r'(臭|味|异味|难闻).{0,3}(柜|鞋|衣|厨)', 
         '鞋柜通风 柜体透气孔 百叶门 防潮 除味 活性炭'),
        (r'(柜|鞋柜|衣柜|橱柜).{0,3}(臭|味|异味|霉|潮)', 
         '鞋柜通风 透气孔 百叶门 防潮 封边 板材环保'),
        (r'(甲醛|TVOC|有害|环保).{0,3}(超标|味|释放)', 
         '板材环保 E0级 封边 通风 检测报告 胶粘剂'),
        
        # --- 漏水/渗水/防水 ---
        (r'(卫生间|厕所|浴室|厨房|阳台).{0,3}(漏水|渗水|滴水|洇)', 
         '防水层 闭水试验 防水涂料 地漏 沉箱防水 48小时'),
        (r'(漏水|渗水|滴水).{0,3}(楼下|邻居|墙|顶)', 
         '防水层 闭水试验 防水涂料 沉箱 二次排水'),
        (r'(防水|闭水).{0,3}(漏|失效|没做|不够)', 
         '闭水试验 48小时 防水涂料 2-3遍 沉箱防水'),
        
        # --- 墙面 ---
        (r'(墙|墙面|墙体).{0,3}(裂|缝|裂纹|起皮|脱落|鼓包)', 
         '腻子层 挂网 乳胶漆 抹灰层 结构裂缝 大白铲除'),
        (r'(起皮|脱落|掉粉|鼓包).{0,3}(墙|顶|腻子)', 
         '大白铲除 腻子层 界面剂 乳胶漆 基层处理'),
        
        # --- 灯/照明 ---
        (r'(灯|照明|射灯|筒灯).{0,3}(闪|频闪|不亮|忽明忽暗)', 
         '零线 智能开关 调光器 镇流器 驱动电源 频闪'),
        (r'(开关|面板).{0,3}(不灵|没反应|跳闸)', 
         '零线 智能开关 单火线 布线 回路'),
        
        # --- 吊顶 ---
        (r'(吊顶|顶|天花).{0,3}(裂|缝|变形|下沉|掉)', 
         '石膏板接缝 木龙骨 轻钢龙骨 转角整板 腻子层开裂'),
        
        # --- 地板 ---
        (r'(地板|木地板).{0,3}(鼓|翘|变形|响|吱)', 
         '防潮膜 地面找平 伸缩缝 受潮膨胀 龙骨'),
        (r'(地板|地面).{0,3}(泡|水|潮|霉)', 
         '防潮膜 地漏 找平 防水 伸缩缝'),
        
        # --- 台面/柜子 ---
        (r'(台面|灶台|操作台).{0,3}(裂|断|渗|染)', 
         '岩板 石英石 挡水条 台面高度 接缝'),
        (r'(柜门|门板|抽屉).{0,3}(碰|撞|关不严|歪)', 
         '铰链 阻尼 柜门间距 动线 开门方向'),
        
        # --- 插座/开关 ---
        (r'(插座|面板|开关).{0,3}(挡|遮|被挡|不够|少)', 
         '放线 1:1模拟 家具遮挡 点位规划 回路'),
        (r'(插座|用电).{0,3}(跳闸|短路|发热)', 
         '线径 回路 空开 漏电保护 分路'),
        
        # --- 门窗 ---
        (r'(门|房门|卧室门).{0,3}(响|吱|关不严|蹭)', 
         '合页 门缝 密封条 门吸 地面找平'),
        (r'(窗|窗户|飘窗).{0,3}(漏|渗|冷|隔音)', 
         '断桥铝 密封胶条 中空玻璃 窗台石 发泡胶'),
    ]
    
    SYSTEM_PROMPT = """你是一个装修领域的检索查询改写专家。用户会用口语化的方式描述装修问题，你需要将其扩展为能命中专业知识库的检索词。

规则：
1. 保留原始查询词
2. 添加同义词/近义词（口语→书面语）
3. 添加对应的专业术语
4. 添加强关联概念（因果、上下位）
5. 总词数控制在8-15个
6. 只输出空格分隔的词组，不要解释"""

    USER_PROMPT_TEMPLATE = "扩展这个装修查询：{query}"
    
    def __init__(self, api_key=None, base_url='https://api.deepseek.com',
                 model='deepseek-chat', timeout=8, cache_size=200):
        """
        Args:
            api_key: DeepSeek API key（默认从环境变量或.env读取）
            base_url: API地址
            model: 模型名
            timeout: 请求超时秒数
            cache_size: LRU缓存容量
        """
        self.api_key = api_key or self._load_api_key()
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.cache = OrderedDict()
        self.cache_size = cache_size
        self.enabled = bool(self.api_key)
        self._stats = {'hits': 0, 'misses': 0, 'errors': 0, 'total_ms': 0,
                       'domain_hits': 0}
        # 预编译正则
        self._compiled_mappings = [
            (re.compile(pattern), terms.split())
            for pattern, terms in self.DOMAIN_MAPPINGS
        ]
    
    def _load_api_key(self):
        """从环境变量或项目.env文件加载API key"""
        key = os.environ.get('DEEPSEEK_API_KEY', '')
        if key:
            return key
        try:
            base = 'D:' + os.sep
            agent_dir = [d for d in os.listdir(base) if 'Agent' in d and os.path.isdir(os.path.join(base, d))][0]
            agent_path = os.path.join(base, agent_dir)
            qw_dir = [d for d in os.listdir(agent_path) if 'AI' in d and os.path.isdir(os.path.join(agent_path, d))][0]
            qw_path = os.path.join(agent_path, qw_dir)
            zs_dir = [d for d in os.listdir(qw_path) if 'zhishe' in d and os.path.isdir(os.path.join(qw_path, d))][0]
            env_path = os.path.join(qw_path, zs_dir, '.env')
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8-sig') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('DEEPSEEK_API_KEY='):
                            return line.split('=', 1)[1].strip()
        except Exception:
            pass
        return ''
    
    def expand(self, query):
        """
        双层扩展（主入口）
        
        Layer 1: 领域映射（始终执行，零延迟）
        Layer 2: LLM扩展（API可用时执行）
        
        Args:
            query: 用户原始查询
        
        Returns:
            str: 扩展后的查询文本（空格分隔词组）
        """
        # 缓存命中
        if query in self.cache:
            self._stats['hits'] += 1
            self.cache.move_to_end(query)
            return self.cache[query]
        
        # Layer 1: 领域映射（确定性，零延迟）
        domain_terms = self._domain_expand(query)
        
        # Layer 2: LLM扩展（广覆盖）
        llm_terms = ''
        if self.enabled:
            llm_terms = self._llm_expand(query)
        
        # 合并：原始query + 领域术语 + LLM扩展（去重）
        combined = self._merge(query, domain_terms, llm_terms)
        
        # 缓存
        self.cache[query] = combined
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        
        return combined
    
    def _domain_expand(self, query):
        """Layer 1: 领域映射扩展（正则匹配）"""
        terms = []
        for pattern, term_list in self._compiled_mappings:
            if pattern.search(query):
                terms.extend(term_list)
                self._stats['domain_hits'] += 1
        # 去重保序
        return list(dict.fromkeys(terms))
    
    def _llm_expand(self, query):
        """Layer 2: DeepSeek LLM扩展"""
        self._stats['misses'] += 1
        t0 = time.time()
        try:
            expanded = self._call_api(query)
            elapsed = (time.time() - t0) * 1000
            self._stats['total_ms'] += elapsed
            if expanded and len(expanded) > len(query):
                # 提取LLM新增的词（去掉原始query部分）
                return expanded
            return ''
        except Exception:
            self._stats['errors'] += 1
            return ''
    
    def _merge(self, query, domain_terms, llm_expanded):
        """合并三层结果，去重"""
        seen = set()
        parts = [query]
        
        # 原始query的词
        for ch in query:
            seen.add(ch)
        
        # 领域术语优先（确定性最高）
        for term in domain_terms:
            if term not in seen and term not in query:
                parts.append(term)
                seen.add(term)
        
        # LLM扩展补充
        if llm_expanded:
            for term in llm_expanded.split():
                if term not in seen and term not in query and len(term) >= 2:
                    parts.append(term)
                    seen.add(term)
        
        return ' '.join(parts)
    
    def _call_api(self, query):
        """调用DeepSeek Chat API"""
        url = f'{self.base_url}/chat/completions'
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': self.SYSTEM_PROMPT},
                {'role': 'user', 'content': self.USER_PROMPT_TEMPLATE.format(query=query)}
            ],
            'temperature': 0.1,
            'max_tokens': 150,
            'stream': False
        }
        
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        
        content = result['choices'][0]['message']['content'].strip()
        content = content.replace('\n', ' ').replace('"', '').replace("'", '')
        return content
    
    def get_stats(self):
        """获取统计信息"""
        avg_ms = self._stats['total_ms'] / max(self._stats['misses'], 1)
        return {
            'cache_hits': self._stats['hits'],
            'api_calls': self._stats['misses'],
            'errors': self._stats['errors'],
            'domain_hits': self._stats['domain_hits'],
            'avg_latency_ms': round(avg_ms, 1),
            'cache_size': len(self.cache),
            'enabled': self.enabled
        }
    
    def reset_stats(self):
        self._stats = {'hits': 0, 'misses': 0, 'errors': 0, 'total_ms': 0,
                       'domain_hits': 0}
