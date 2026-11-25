# -*- coding: utf-8 -*-
import webview
from logger import get_logger

# 全局变量用于存储选择结果
selection_result = None
window = None

# 将 HTML 内容定义在函数外部，使其可以被导入
html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>keyboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            color: #fff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 5px;
            background: #2b2b2b;
        }
        
        .header {
            margin-bottom: 20px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 24px;
            margin-bottom: 10px;
            color: #fff;
        }
        
        .header .info {
            color: #ccc;
            font-size: 14px;
        }
        
        .keyboard-container {
            background: #b3b4b3;
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            margin-bottom: 30px;
            position: relative;
            overflow: hidden;
        }
        
        .keyboard {
            position: relative;
            width: 1100px;
            height: 320px;
            background: #b3b4b3;
        }
        
        .key {
            position: absolute;
            border: 1px solid rgba(0,0,0,0.7);
            border-radius: 8px;
            padding: 3.5px 6px 8px 6px;
            transition: all 0.16s ease-in-out;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10.5px;
            font-weight: 500;
            cursor: pointer;
            user-select: none;
            box-shadow: 
                0 0 0 1px rgba(16,22,26,0.1),
                0 1px 1px rgba(16,22,26,0.2),
                0 1px 1px rgba(16,22,26,0.2);
        }
        
        .key:hover {
            filter: brightness(1.08);
            transform: translateY(-2px);
        }
        
        .key:active {
            transform: translateY(1px);
        }
        
        .key.active {
            background: rgb(100, 171, 63) !important;
            color: rgb(249, 249, 249) !important;
        }
        
        .key-inner {
            width: 100%;
            height: 100%;
            border: 1px solid rgba(0,0,0,0.25);
            box-shadow: 0 2px 1px rgba(0, 0, 0, 0.25);
            border-radius: 5px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            position: relative;
        }
        
        /* 不同功能键的颜色 */
        .key.system { background: #545454; color: #fe532b; }
        .key.standard { background: #f5f5f5; color: #000; }
        .key.function { background: #545454; color: #e2dcce; }
        .key.modifier { background: #545454; color: #d9ccfc; }
        .key.caps { background: #545454; color: #b2f274; }
        .key.shift { background: #545454; color: #f48549; }
        .key.ctrl { background: #545454; color: #46c5f4; }
        .key.win { background: #545454; color: #fe532b; }
        .key.alt { background: #545454; color: #46c5f4; }
        .key.mouse { background: #67546b; color: #ffffff; font-size: 10px; }
        .key.mouse-wheel { background: #67546b; color: #ffffff; font-size: 9px; }
        .key.disabled { opacity: 0.6; cursor: not-allowed; }
        .key.disabled:hover { filter: none; transform: none; }
        
        /* 特殊键的样式 */
        .key.home-row::after {
            content: "";
            position: absolute;
            bottom: 8px;
            left: 50%;
            transform: translateX(-50%);
            width: 6px;
            height: 1.5px;
            background: #64748b;
            border-radius: 1px;
            box-shadow: 0 0 2px rgba(0,0,0,0.3);
        }
        
        .key.wide { width: 98px; }
        .key.extra-wide { width: 306px; }
        .key.tall { height: 98px; }
        .key.small { width: 40px; height: 40px; font-size: 8px; padding: 2px 3px 4px 3px; }
        .key.very-small { width: 35px; height: 35px; font-size: 7px; padding: 1px 2px 3px 2px; }
        .key.flat { width: 40px; height: 25px; font-size: 10px; padding: 1px 2px 2px 2px; }
        
        /* 控制按钮区域 */
        .controls {
            display: flex;
            gap: 15px;
            margin-top: 20px;
        }
        
        .control-btn {
            padding: 12px 30px;
            font-size: 16px;
            font-weight: bold;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .confirm-btn {
            background: #4CAF50;
            color: white;
        }
        
        .confirm-btn:hover {
            background: #45a049;
        }
        
        .confirm-btn:disabled {
            background: #cccccc;
            cursor: not-allowed;
        }
        
        .cancel-btn {
            background: #f44336;
            color: white;
        }
        
        .cancel-btn:hover {
            background: #da190b;
        }
        
        .selection-info {
            margin-top: 15px;
            padding: 10px;
            background: #3a3a3a;
            border-radius: 5px;
            min-width: 300px;
            text-align: center;
        }
        
        .selected-keys {
            color: #4CAF50;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="info">请选择1-3个按键组合（支持键盘和鼠标按键）</div>
    </div>
    
    <div class="keyboard-container">
        <div class="keyboard" id="keyboard">
            <!-- 键盘布局将通过JavaScript动态生成 -->
        </div>
    </div>
    
    <div class="selection-info">
        已选择: <span class="selected-keys" id="selectedKeys">无</span>
    </div>
    
    <div class="controls">
        <button class="control-btn confirm-btn" id="confirmBtn" disabled>确定</button>
        <button class="control-btn cancel-btn" id="cancelBtn">取消</button>
    </div>

    <script>
        // 键盘布局数据
        const keyboardLayout = [
            // 第一行 - 功能键
            { label: "Esc", x: 0, y: 0, width: 49, height: 49, type: "system" },
            { label: "F1", x: 98, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F2", x: 147, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F3", x: 196, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F4", x: 245, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F5", x: 318.5, y: 0, width: 49, height: 49, type: "function" },
            { label: "F6", x: 367.5, y: 0, width: 49, height: 49, type: "function" },
            { label: "F7", x: 416.5, y: 0, width: 49, height: 49, type: "function" },
            { label: "F8", x: 465.5, y: 0, width: 49, height: 49, type: "function" },
            { label: "F9", x: 539, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F10", x: 588, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F11", x: 637, y: 0, width: 49, height: 49, type: "standard" },
            { label: "F12", x: 686, y: 0, width: 49, height: 49, type: "standard" },
            
            // 第二行 - 数字行
            { label: "`", x: 0, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "1", x: 49, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "2", x: 98, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "3", x: 147, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "4", x: 196, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "5", x: 245, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "6", x: 294, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "7", x: 343, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "8", x: 392, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "9", x: 441, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "0", x: 490, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "-", x: 539, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "=", x: 588, y: 73.5, width: 49, height: 49, type: "standard" },
            { label: "Backspace", x: 637, y: 73.5, width: 98, height: 49, type: "modifier" },
            { label: "Insert", x: 747.25, y: 73.5, width: 49, height: 49, type: "function" },
            { label: "Home", x: 796.25, y: 73.5, width: 49, height: 49, type: "function" },
            { label: "PgUp", x: 845.25, y: 73.5, width: 49, height: 49, type: "function" },
            { label: "Lock", x: 906.5, y: 73.5, width: 49, height: 49, type: "system" },
            { label: "/", x: 955.5, y: 73.5, width: 49, height: 49, type: "function", selectable: false },
            { label: "*", x: 1004.5, y: 73.5, width: 49, height: 49, type: "function", selectable: false },
            { label: "-", x: 1053.5, y: 73.5, width: 49, height: 49, type: "function", selectable: false },
            
            // 第三行 - QWERTY行
            { label: "Tab", x: 0, y: 122.5, width: 73.5, height: 49, type: "modifier" },
            { label: "Q", x: 73.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "W", x: 122.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "E", x: 171.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "R", x: 220.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "T", x: 269.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "Y", x: 318.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "U", x: 367.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "I", x: 416.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "O", x: 465.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "P", x: 514.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "[", x: 563.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "]", x: 612.5, y: 122.5, width: 49, height: 49, type: "standard" },
            { label: "\\\\", x: 661.5, y: 122.5, width: 73.5, height: 49, type: "standard" },
            { label: "Delete", x: 747.25, y: 122.5, width: 49, height: 49, type: "function" },
            { label: "End", x: 796.25, y: 122.5, width: 49, height: 49, type: "function" },
            { label: "PgDn", x: 845.25, y: 122.5, width: 49, height: 49, type: "function" },
            { label: "鼠标左键", x: 906.5, y: 122.5, width: 49, height: 49, type: "mouse" },
            { label: "鼠标中键", x: 955.5, y: 122.5, width: 49, height: 49, type: "mouse" },
            { label: "鼠标右键", x: 1004.5, y: 122.5, width: 49, height: 49, type: "mouse" },
            { label: "+", x: 1053.5, y: 122.5, width: 49, height: 98, type: "function", selectable: false },
            
            // 第四行 - ASDF行
            { label: "CapsLock", x: 0, y: 171.5, width: 85.75, height: 49, type: "caps" },
            { label: "A", x: 85.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "S", x: 134.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "D", x: 183.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "F", x: 232.75, y: 171.5, width: 49, height: 49, type: "standard", homeRow: true },
            { label: "G", x: 281.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "H", x: 330.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "J", x: 379.75, y: 171.5, width: 49, height: 49, type: "standard", homeRow: true },
            { label: "K", x: 428.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "L", x: 477.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: ";", x: 526.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "'", x: 575.75, y: 171.5, width: 49, height: 49, type: "standard" },
            { label: "Enter", x: 624.75, y: 171.5, width: 110.25, height: 49, type: "caps" },
            { label: "鼠标侧键2", x: 906.5, y: 171.5, width: 49, height: 49, type: "mouse" },
            { label: "滚轮上", x: 955.5, y: 171.5, width: 49, height: 49, type: "mouse-wheel", selectable: false  },
            { label: "6", x: 1004.5, y: 171.5, width: 49, height: 49, type: "standard", selectable: false },
            
            // 第五行 - ZXCV行
            { label: "LShift", x: 0, y: 220.5, width: 110.25, height: 49, type: "shift" },
            { label: "Z", x: 110.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "X", x: 159.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "C", x: 208.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "V", x: 257.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "B", x: 306.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "N", x: 355.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "M", x: 404.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: ",", x: 453.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: ".", x: 502.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "/", x: 551.25, y: 220.5, width: 49, height: 49, type: "standard" },
            { label: "RShift", x: 600.25, y: 220.5, width: 134.75, height: 49, type: "shift" },
            { label: "↑", x: 796.25, y: 220.5, width: 49, height: 49, type: "function" },
            { label: "鼠标侧键1", x: 906.5, y: 220.5, width: 49, height: 49, type: "mouse" },
            { label: "滚轮下", x: 955.5, y: 220.5, width: 49, height: 49, type: "mouse-wheel", selectable: false  },
            { label: "3", x: 1004.5, y: 220.5, width: 49, height: 49, type: "standard", selectable: false },
            { label: "N.Ent", x: 1053.5, y: 220.5, width: 49, height: 98, type: "caps", selectable: false },
            
            // 第六行 - 空格行
            { label: "LCtrl", x: 0, y: 269.5, width: 61.25, height: 49, type: "ctrl" },
            { label: "LWin", x: 61.25, y: 269.5, width: 61.25, height: 49, type: "win" },
            { label: "LAlt", x: 122.5, y: 269.5, width: 61.25, height: 49, type: "alt" },
            { label: "Space", x: 183.75, y: 269.5, width: 306.25, height: 49, type: "standard" },
            { label: "RAlt", x: 490, y: 269.5, width: 61.25, height: 49, type: "alt" },
            { label: "RWin", x: 551.25, y: 269.5, width: 61.25, height: 49, type: "win" },
            { label: "Menu", x: 612.5, y: 269.5, width: 61.25, height: 49, type: "alt" },
            { label: "RCtrl", x: 673.75, y: 269.5, width: 61.25, height: 49, type: "ctrl" },
            { label: "←", x: 747.25, y: 269.5, width: 49, height: 49, type: "function" },
            { label: "↓", x: 796.25, y: 269.5, width: 49, height: 49, type: "function" },
            { label: "→", x: 845.25, y: 269.5, width: 49, height: 49, type: "function" },
            { label: "0", x: 906.5, y: 269.5, width: 98, height: 49, type: "standard", selectable: false },
            { label: ".", x: 1004.5, y: 269.5, width: 49, height: 49, type: "standard", selectable: false }
        ];

        // 选中的按键集合
        let selectedKeys = new Set();
        let selectedKeyData = new Map(); // 存储按键的完整信息

        // 生成键盘布局
        function renderKeyboard() {
            const keyboard = document.getElementById('keyboard');
            
            keyboardLayout.forEach(key => {
                const keyElement = document.createElement('div');
                keyElement.className = `key ${key.type}`;
                
                // 设置位置和尺寸
                keyElement.style.width = `${key.width}px`;
                keyElement.style.height = `${key.height}px`;
                keyElement.style.left = `${key.x}px`;
                keyElement.style.top = `${key.y}px`;
                
                // 处理多行标签
                const lines = key.label.split('\\\\n');
                let labelHTML = '';
                
                if (lines.length > 1) {
                    labelHTML = `<span>${lines[0]}</span><span>${lines[1]}</span>`;
                } else {
                    labelHTML = `<span>${key.label}</span>`;
                }
                
                keyElement.innerHTML = `
                    <div class="key-inner">
                        ${labelHTML}
                    </div>
                `;
                
                // 添加定位标识
                if (key.homeRow) {
                    keyElement.classList.add('home-row');
                }
                
                // 添加尺寸类
                if (key.size === 'small') {
                    keyElement.classList.add('small');
                } else if (key.size === 'very-small') {
                    keyElement.classList.add('very-small');
                } else if (key.size === 'flat') {
                    keyElement.classList.add('flat');
                }
                
                // 添加宽键类
                if (key.width > 60) {
                    keyElement.classList.add('wide');
                }
                
                if (key.width > 200) {
                    keyElement.classList.add('extra-wide');
                }
                
                if (key.height > 60) {
                    keyElement.classList.add('tall');
                }
                
                // 对于不可选择的键，禁用点击事件并添加禁用样式
                if (key.selectable === false) {
                    keyElement.classList.add('disabled');
                    keyElement.style.cursor = 'not-allowed';
                    keyElement.onclick = null;
                } else {
                    // 添加点击事件 - 选择/取消选择按键
                    keyElement.addEventListener('click', () => {
                        const keyId = key.label;
                        
                        if (selectedKeys.has(keyId)) {
                            // 取消选择
                            selectedKeys.delete(keyId);
                            selectedKeyData.delete(keyId);
                            keyElement.classList.remove('active');
                        } else {
                            // 检查是否已达到最大选择数量
                            if (selectedKeys.size >= 3) {
                                alert('最多只能选择3个按键！');
                                return;
                            }
                            
                            // 选择按键
                            selectedKeys.add(keyId);
                            selectedKeyData.set(keyId, key);
                            keyElement.classList.add('active');
                        }
                        
                        // 更新显示
                        updateSelectionDisplay();
                        
                        // 更新确定按钮状态
                        document.getElementById('confirmBtn').disabled = selectedKeys.size === 0;
                        
                        console.log(`选择按键: ${keyId}, 当前选择: ${Array.from(selectedKeys).join(', ')}`);
                    });
                }
                
                keyboard.appendChild(keyElement);
            });
        }

        // 更新选择显示
        function updateSelectionDisplay() {
            const selectedKeysElement = document.getElementById('selectedKeys');
            if (selectedKeys.size === 0) {
                selectedKeysElement.textContent = '无';
            } else {
                selectedKeysElement.textContent = Array.from(selectedKeys).join(' & ');
            }
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', () => {
            renderKeyboard();
            
            // 确定按钮事件
            document.getElementById('confirmBtn').addEventListener('click', () => {
                if (selectedKeys.size > 0) {
                    // 将选择结果发送回 Python
                    const result = Array.from(selectedKeys).join('&');
                    window.pywebview.api.returnResult(result);
                }
            });
            
            // 取消按钮事件
            document.getElementById('cancelBtn').addEventListener('click', () => {
                window.pywebview.api.returnResult(null);
            });
        });
    </script>
</body>
</html>
"""

class Api:
    def __init__(self):
        pass
    
    def returnResult(self, result):
        """JavaScript 调用此方法来返回结果"""
        global selection_result, window
        selection_result = result
        logger = get_logger()
        logger.info(f"用户选择: {result}")
        
        # 关闭窗口
        if window:
            window.destroy()

def select_keys():
    """
    打开键盘选择窗口并返回用户选择的结果
    
    Returns:
        str or None: 用户选择的按键组合（如 "Ctrl+C"），取消则返回 None
    """
    global selection_result, window
    
    # 重置结果
    selection_result = None
    
    # 创建 API 实例
    api = Api()
    
    # 创建窗口
    window = webview.create_window(
        'keyboard',
        html=html_content,
        width=1200,
        height=640,
        resizable=False,
        background_color='#2b2b2b',
        js_api=api
    )
    
    logger = get_logger()
    logger.debug("请选择按键组合...")
    
    # 启动窗口（这会阻塞直到窗口关闭）
    webview.start()
    
    # 返回选择结果
    return selection_result

if __name__ == '__main__':
    # 直接运行时的示例
    logger = get_logger()
    selected_keys = select_keys()
    if selected_keys:
        logger.info(f"最终选择的按键组合: {selected_keys}")
    else:
        logger.debug("用户取消了选择")