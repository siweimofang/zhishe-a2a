// ============================================================
// RenovationConsultAbility.ets
// 知设 AI 装修顾问 V1.7 鸿蒙版 - V0.2 全国 + 沈阳双层定位
// 文件位置:entry/src/main/ets/entryability/RenovationConsultAbility.ets
// ============================================================

import { AbilityConstant, ConfigurationConstant, UIAbility, Want } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { http } from '@kit.NetworkKit';
import { BusinessError } from '@kit.BasicServicesKit';

const DOMAIN = 0x0000;
const TAG = 'RenovationConsultAbility';

// zhishe-a2a 永久 URL + API Key
const ZHISHE_A2A_URL = 'https://tunnel.zhishe.top/v1/chat/completions';
const ZHISHE_API_KEY = 'mKgd4EVhF7A8Y9zk6unOyb2jI1NBLaTR';

export default class RenovationConsultAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam) {
    hilog.info(DOMAIN, TAG, 'RenovationConsultAbility V0.2 onCreate');

    // 接收小艺主对话传来的"用户问题" + 意图 ID
    const userQuery = want.parameters?.user_query as string;
    const intentId = want.parameters?.intent_id as string;
    const sessionId = want.parameters?.session_id as string;

    // 意图路由
    if (intentId === 'zhishe.renovation.intro' ||
        userQuery?.includes('你好') ||
        userQuery?.includes('在吗') ||
        userQuery?.includes('介绍')) {
      // 首次对话:走"提示词自我介绍"分支
      this.selfIntroduction();
    } else if (intentId === 'zhishe.renovation.wechat' ||
               userQuery?.includes('加微信') ||
               userQuery?.includes('联系方式') ||
               userQuery?.includes('咨询')) {
      // 转化引导分支
      this.wechatGuide();
    } else {
      // 其他意图:调 zhishe-a2a 永久 URL
      if (userQuery) {
        this.callZhisheA2A(userQuery, sessionId);
      }
    }
  }

  async callZhisheA2A(userQuery: string, sessionId: string) {
    const httpRequest = http.createHttp();

    const requestBody = {
      model: 'deepseek-v4-pro',
      messages: [
        {
          role: 'user',
          content: userQuery
        }
      ],
      max_tokens: 1500,
      temperature: 0.7,
      stream: false
    };

    try {
      const response = await httpRequest.request(ZHISHE_A2A_URL, {
        method: http.RequestMethod.POST,
        header: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${ZHISHE_API_KEY}`
        },
        extraData: JSON.stringify(requestBody),
        connectTimeout: 60000,
        readTimeout: 60000
      });

      if (response.responseCode === 200) {
        const result = JSON.parse(response.result as string);
        const answer = result.choices[0].message.content;

        // 通过 hilog 输出,小艺智能体框架会自动捕获
        hilog.info(DOMAIN, TAG, `zhishe-a2a answer: ${answer}`);

        // 可选:写入 HarmonyOS 分布式数据(给后续 Service Extension Ability 调用)
        // dataPreferences.putStringSync('last_answer', answer);
      } else {
        hilog.error(DOMAIN, TAG, `zhishe-a2a HTTP ${response.responseCode}`);
      }
    } catch (err) {
      const error = err as BusinessError;
      hilog.error(DOMAIN, TAG, `zhishe-a2a error: ${error.code} ${error.message}`);
    } finally {
      httpRequest.destroy();
    }
  }

  // V0.2 升级:从"沈阳本地" → "全国 + 沈阳双层定位"
  selfIntroduction() {
    const intro = `👋 您好!我是「知设 AI 装修顾问」。

【V0.2 双层定位】
• 主力:全国装修 AI 顾问(覆盖 30+ 城市,智能识别你的城市)
• 深耕:沈阳本地价格精准(8 年老法师深耕,沈阳本地实测)

【我能帮你】
• 📊 出 2026 Q2 装修报价(半包 350-1300/大包 700-5000/全案一房一价,4 档)
• 🏙️ 智能识别你所在城市,自动应用城市系数(北京/上海/广州/深圳 +10-15%,西部 -5-10%)
• 🌧️ 南方梅雨季 / 北方供暖季 施工差异智能提醒
• 📋 装修全流程节点(量房 → 设计 → 拆改 → 水电 → ... → 入住)
• 🛡️ 水/电/瓦/木/油 9 道工序避坑指南(老法师经验)
• 🛒 推 13 城主流建材市场(沈阳 3 大市场 / 北京居然之家 / 上海红星美凯龙 等)
• 🏷️ 全国主流品牌识别(伟星水管 / 立邦乳胶漆 / 圣象地板 / 欧派 / 索菲亚 / 志邦)

【数据来源】
国标 GB 50327-2001 / GB 50150-2016 / GB 50210
伟星 vasen.com 防伪官网(18 位防伪)
2026 Q2 全国 13 城装修市场调研 + 沈阳本地实测价

【免责声明】
不替用户做最终决定,所有信息仅供参考,签约前请以实际勘察和合同为准。`;

    hilog.info(DOMAIN, TAG, `V0.2 intro: ${intro}`);
  }

  // V0.2 升级:从"沈阳装修报价清单" → "全国 + 沈阳双层报价清单"
  wechatGuide() {
    const guide = `装修水深,我整理了一份《2026 全国 + 沈阳装修报价清单》PDF,加我微信 sxxxxx 发你,免费帮你看报价。`;
    hilog.info(DOMAIN, TAG, `V0.2 wechat guide: ${guide}`);
  }

  onDestroy() {
    hilog.info(DOMAIN, TAG, 'RenovationConsultAbility V0.2 onDestroy');
  }

  onConfigurationUpdated(newConfig: ConfigurationConstant.Configuration) {
    hilog.info(DOMAIN, TAG, 'RenovationConsultAbility V0.2 onConfigurationUpdated');
  }
}
