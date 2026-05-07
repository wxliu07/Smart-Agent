# 安装依赖 pip3 install requests html5lib bs4 schedule

import time
import requests
import json
import schedule
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import re
import random

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== 配置信息 ====================
# 从测试号信息获取
appID = "wx61de1ed06f3e0739"
appSecret = "cb493f6e89285f747c58c2555274e392"
# 收信人ID即用户列表中的微信号
openId = "oSHZe3Fq3nhvIygPO4WySzAWxQ5Q"
# 天气预报模板ID
weather_template_id = "ogjGwhkZj4nMdO_U7CycKNj-DuenLLy6DBHrQ9_SLbo"
# 时间表模板ID
timetable_template_id = "ejxXaj93Wv1W7ax715AGqD6KLtYnECtyVVc9OZBra9A"

# ==================== 高德天气API配置 ====================
AMAP_API_KEY = "cb01b0bddff2fa9e29fb62c5f453b54d"
AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

# 星期映射
WEEKDAY_MAP = {
    '1': '星期一',
    '2': '星期二',
    '3': '星期三',
    '4': '星期四',
    '5': '星期五',
    '6': '星期六',
    '7': '星期日'
}

# 天气消息模板
MESSAGE_PROMPT = "日期: {}, 白天温度: {}℃, 晚上温度: {}℃, 白天天气: {}, 晚上天气: {}"
WEATHER_PROMPT = "{}天气预报:\n今天: {}{}"


# ==================== 天气获取函数 ====================
def _get_weather(location: str):
    """帮助用户想要查询的天气"""
    params = {
        'key': AMAP_API_KEY,
        'city': location,
        'extensions': 'all'
    }

    try:
        res = requests.get(url=AMAP_WEATHER_URL, params=params, timeout=5)
        result = res.json()

        if result.get('status') != '1':
            logger.error(f"API返回错误: {result.get('info')}")
            return f"查询天气失败: {result.get('info')}"

        city = result.get('forecasts')[0].get("city")
        message_result = []
        data = result.get('forecasts')[0].get("casts")
        print("=" * 10)
        print(f"data: {data}")
        print("=" * 10)

        for item in data:
            date = item.get('date')
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%m月%d日")

            day_temp = item.get('daytemp')
            night_temp = item.get('nighttemp')
            day_weather = item.get('dayweather')
            night_weather = item.get('nightweather')

            weather_message = MESSAGE_PROMPT.format(formatted_date, day_temp, night_temp, day_weather, night_weather)
            message_result.append(weather_message)

        if len(message_result) > 1:
            final_result = WEATHER_PROMPT.format(city, message_result[0], '\n'.join([''] + message_result[1:]))
        else:
            final_result = WEATHER_PROMPT.format(city, message_result[0], '')

        return final_result

    except requests.exceptions.RequestException as req_err:
        logger.error(f'请求天气API失败: {req_err}')
        return f"网络请求失败: {req_err}"
    except Exception as err:
        logger.error(f'调用天气工具出错: {err}')
        return f"获取天气信息失败: {err}"


def get_weather_simple(city):
    """
    获取简化的天气信息，用于微信模板消息
    返回: (城市, 温度范围, 天气类型, 温馨提醒)
    """
    weather_info = _get_weather(city)

    if weather_info.startswith("查询天气失败") or weather_info.startswith("网络请求失败") or weather_info.startswith(
            "获取天气信息失败"):
        print(f"获取天气失败: {weather_info}")
        return city, "暂无温度数据", "暂无天气数据", "暂无提醒"

    try:
        lines = weather_info.split('\n')
        city_name = lines[0].replace("天气预报:", "")

        today_line = lines[1] if len(lines) > 1 else ""

        if "白天温度:" in today_line and "晚上温度:" in today_line and "白天天气:" in today_line:
            day_temp = re.search(r'白天温度: (\d+)℃', today_line)
            night_temp = re.search(r'晚上温度: (\d+)℃', today_line)
            day_weather = re.search(r'白天天气: ([^,]+)', today_line)
            night_weather = re.search(r'晚上天气: ([^,]+)', today_line)

            day_temp_val = day_temp.group(1) if day_temp else "?"
            night_temp_val = night_temp.group(1) if night_temp else "?"
            day_weather_val = day_weather.group(1) if day_weather else "?"
            night_weather_val = night_weather.group(1) if night_weather else "?"

            temp_range = f"{night_temp_val}摄氏度 ~ {day_temp_val}摄氏度"

            # 生成温馨提醒
            weather_tip = generate_weather_tip(day_temp_val, night_temp_val, day_weather_val, night_weather_val)

            return city_name.strip(), temp_range, day_weather_val, weather_tip
        else:
            return city_name.strip(), "温度数据异常", "天气数据异常", "暂无提醒"

    except Exception as e:
        print(f"解析天气数据失败: {e}")
        return city, "解析失败", "解析失败", "解析失败"


def generate_weather_tip(day_temp, night_temp, day_weather, night_weather):
    """根据天气生成温馨提醒"""
    tips = []

    # 温度提醒
    day_temp_int = int(day_temp) if day_temp != "?" else 20
    night_temp_int = int(night_temp) if night_temp != "?" else 15

    if day_temp_int >= 30:
        tips.append("高温天气，注意防暑降温")
    elif day_temp_int <= 5:
        tips.append("严寒天气，注意保暖")
    elif day_temp_int <= 10:
        tips.append("天气较冷，注意保暖")

    # 天气提醒
    if '雨' in day_weather or '雨' in night_weather:
        if '大' in day_weather or '暴' in day_weather:
            tips.append("大雨天气，出门带伞，注意安全")
        else:
            tips.append("今天有雨，出门记得带伞")

    if '雪' in day_weather or '雪' in night_weather:
        tips.append("今天有雪，注意防滑保暖")

    if '雾' in day_weather or '霾' in day_weather:
        tips.append("空气质量不佳，建议佩戴口罩")

    if '晴' in day_weather:
        if day_temp_int > 25:
            tips.append("天气晴朗，紫外线较强，注意防晒")
        else:
            tips.append("天气晴朗，适合户外活动")

    if '云' in day_weather:
        tips.append("多云天气，适合出行")

    # 温差提醒
    temp_diff = day_temp_int - night_temp_int
    if temp_diff > 15:
        tips.append("昼夜温差大，注意适时增减衣物")
    elif temp_diff > 10:
        tips.append("早晚温差较大，建议带件外套")

    return " ".join(tips) if tips else "天气不错，祝您有美好的一天！"


# ==================== 微信API函数 ====================
def get_access_token():
    """获取微信access_token"""
    url = 'https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={}&secret={}' \
        .format(appID.strip(), appSecret.strip())
    response = requests.get(url).json()
    print(f"获取access_token响应: {response}")
    access_token = response.get('access_token')
    return access_token


def get_daily_love():
    """获取每日一句情话（确保不超过19个字符）"""
    max_attempts = 5
    attempt = 0

    while attempt < max_attempts:
        try:
            url = "https://api.lovelive.tools/api/SweetNothings/Serialization/Json"
            r = requests.get(url, timeout=5)
            all_dict = json.loads(r.text)
            sentence = all_dict['returnObj'][0]

            # 检查字符数（中文字符每个算1个）
            if len(sentence) >= 18:
                print(f"情话内容: {sentence}")
                return sentence
            else:
                print(f"情话太短（{len(sentence)}字符），重新获取...")
                attempt += 1

        except Exception as e:
            print(f"获取每日情话失败: {e}")
            attempt += 1

    # 默认短句
    default_love = [
        "今天也要开心哦",
        "愿你有个好心情",
        "美好的一天开始",
        "记得多喝热水",
        "要照顾好自己",
        "今天想你了",
        "早安，亲爱的",
        "祝你今天顺利",
        "你笑起来真好看",
        "今天也要加油",
        "保持好心情",
        "天气不错呢"
    ]
    return random.choice(default_love)


def send_weather(access_token, weather):
    """发送天气模板消息"""
    import datetime
    today = datetime.date.today()
    today_str = today.strftime("%Y年%m月%d日")

    # 获取星期几
    week_num = str(today.weekday() + 1)
    weekday = WEEKDAY_MAP.get(week_num, "")

    body = {
        "touser": openId.strip(),
        "template_id": weather_template_id.strip(),
        "url": "https://weixin.qq.com",
        "data": {
            "date": {
                "value": f"{today_str} - {weekday}"  # 日期 + 星期
            },
            "region": {
                "value": weather[0]  # 城市
            },
            "weather": {
                "value": weather[2]  # 天气类型
            },
            "temp": {
                "value": weather[1]  # 温度
            },
            "tip": {  # 温馨提醒（替换原来的wind_dir）
                "value": weather[3]  # 温馨提醒
            },
            "today_note": {
                "value": get_daily_love()  # 每日情话
            }
        }
    }
    url = 'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={}'.format(access_token)
    headers = {'Content-Type': 'application/json'}
    print(requests.post(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers).text)


def send_timetable(access_token, message):
    """发送课表模板消息"""
    body = {
        "touser": openId,
        "template_id": timetable_template_id.strip(),
        "url": "https://weixin.qq.com",
        "data": {
            "message": {
                "value": message
            },
        }
    }
    url = 'https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={}'.format(access_token)
    headers = {'Content-Type': 'application/json'}
    print(requests.post(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers).text)


def weather_report(city):
    """天气报告主函数"""
    print(f"开始获取 {city} 的天气信息...")

    # 1. 获取access_token
    access_token = get_access_token()
    if not access_token:
        print("获取access_token失败，程序退出")
        return

    # 2. 获取天气（返回4个值）
    weather = get_weather_simple(city)
    print(f"天气信息： {weather}")

    # 3. 发送消息
    send_weather(access_token, weather)


def timetable(message):
    """课表发送主函数"""
    print(f"开始发送课表消息: {message}")

    # 1. 获取access_token
    access_token = get_access_token()
    if not access_token:
        print("获取access_token失败，程序退出")
        return

    # 2. 发送消息
    send_timetable(access_token, message)


if __name__ == '__main__':
    # 测试天气查询
    print("=" * 50)
    print("测试高德天气API")
    print("=" * 50)

    print("\n" + "=" * 50)
    print("发送微信模板消息")
    print("=" * 50)

    # 发送微信模板消息
    weather_report("成都")