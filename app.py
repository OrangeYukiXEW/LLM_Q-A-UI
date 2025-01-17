# app.py
import streamlit as st
import pandas as pd
import PyPDF2  # 用于解析 PDF 
import re  # 用于正则表达式提取问题
from config.config import *
from request.api_request import get_response
import os


# 分批处理问题
def batch_process_questions(api_key, app_id, workspace, questions, batch_size=5):
    results = []
    for i in range(0, len(questions), batch_size):
        batch = questions[i:i + batch_size]
        st.sidebar.write(f"正在处理第 {i + 1} 到 {i + len(batch)} 个问题...")
        for question in batch:
            messages = [("用户", question)]
            response = get_response(api_key, app_id, messages, workspace)
            results.append({"问题": question, "回答": response, "分数": "0"})
    return results

# Function to extract questions from a text
def extract_questions(text):
    # 使用正则表达式提取问题（以问号结尾的句子）
    questions = re.findall(r'[^。！？]*[？?]', text)
    # 去除空白字符
    questions = [q.strip() for q in questions if q.strip()]
    return questions

# Function to parse uploaded file
def parse_file(uploaded_file):
    if uploaded_file.type == "text/plain":
        # 解析 TXT 文件
        text = uploaded_file.read().decode("utf-8")
        return extract_questions(text)
    elif uploaded_file.type == "application/pdf":
        # 解析 PDF 文件
        pdf_reader = PyPDF2.PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return extract_questions(text)
    elif uploaded_file.type in ["application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]:
        # 解析 Excel 文件
        df = pd.read_excel(uploaded_file)
        # 假设问题在某一列中（例如 "问题" 列）
        if "问题" in df.columns:
            return df["问题"].tolist()
        else:
            st.error(f"{uploaded_file.name} 中未找到 '问题' 列！")
            return []
    elif uploaded_file.type == "text/csv":
        # 解析 CSV 文件
        df = pd.read_csv(uploaded_file)
        if "问题" in df.columns:
            return df["问题"].tolist()
        else:
            st.error(f"{uploaded_file.name} 中未找到 '问题' 列！")
            return []
    else:
        st.error(f"文件 {uploaded_file.name} 的类型不支持！")
        return []

# Streamlit app layout
st.title("大模型测试平台")

# Sidebar for configuration
st.sidebar.header("设置")

# 选择配置模式
config_mode = st.sidebar.selectbox(
    "选择配置模式",
    ["选择配置", "新增配置"],
    index=0  # 默认选择选择配置
)

# 根据选择的模式显示不同的配置选项
if config_mode == "选择配置":
    config_file = st.sidebar.selectbox(
    "选择配置文件", 
    [f for f in os.listdir("config") if f.endswith('.txt')],
    index=0
)
    config=load_config_from_file(f"config/{config_file}")
    api_key = config["DEFAULT_API_KEY"]
    app_id = config["DEFAULT_APP_ID"]
    workspace = config["DEFAULT_WORKSPACE"]
else:
    # 新增配置
    api_key = st.sidebar.text_input("API Key", placeholder="请输入您的 API Key")
    app_id = st.sidebar.text_input("应用 ID", placeholder="请输入您的应用 ID")
    workspace = st.sidebar.text_input("Workspace", placeholder="请输入您的 Workspace")
    file_name = st.sidebar.text_input("配置文件名", placeholder="请输入您创建的配置文件名称")

    if st.sidebar.button("确认新增并应用") and api_key and app_id and workspace:
        file_name = r"config/{}.txt".format(file_name)
        creat_config_to_file(file_name, api_key, app_id, workspace)

# File uploader (支持批量上传)
st.sidebar.header("上传文件")
uploaded_files = st.sidebar.file_uploader(
    "上传文件（支持 TXT、PDF、CSV、Excel），可多选",
    type=["txt", "pdf", "csv", "xlsx"],
    accept_multiple_files=True
)

# Main chat window
st.header("对话窗口")
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Input box for user message
user_message = st.text_input("输入你的消息", placeholder="请输入您的问题后点击发送")

if st.button("发送"):
    if api_key and app_id and user_message.strip():
        # Save user message to session state
        st.session_state["messages"].append(("用户", user_message.strip()))
        # Get response from the API with full context
        response = get_response(api_key, app_id, st.session_state["messages"], workspace)
        # Save assistant's response to session state
        st.session_state["messages"].append(("深大招生助手", response))
        # Clear input box after sending
        st.rerun()
    else:
        st.error("请确保 API Key、应用 ID 和消息均已填写！")

# Display chat messages
for sender, message in st.session_state["messages"]:
    st.write(f"**{sender}**: {message}")

# Process uploaded files
if uploaded_files:
    st.sidebar.write("文件已上传，正在解析...")
    if "file_results" not in st.session_state:
        st.session_state["file_results"] = {}

    for uploaded_file in uploaded_files:
        st.sidebar.write(f"正在处理文件: {uploaded_file.name}")
        questions = parse_file(uploaded_file)
        if questions:
            st.sidebar.write(f"从 {uploaded_file.name} 提取到的问题：")
            for i, question in enumerate(questions):
                st.sidebar.write(f"{i + 1}. {question}")

            # 在自动对话中使用分批处理
            if st.sidebar.button(f"开始自动对话 - {uploaded_file.name}"):
                if not api_key or not app_id:
                    st.sidebar.error("请确保 API Key 和 App ID 均已填写！")
                else:
                    results = batch_process_questions(api_key, app_id, workspace, questions)
                    # Save results to session state
                    st.session_state["file_results"][uploaded_file.name] = pd.DataFrame(results)
                    st.sidebar.success(f"文件 {uploaded_file.name} 的对话完成，结果已保存！")


# 新增：保存结果到用户指定路径
def save_to_local_path(results_df, default_file_name, sidebar_key):
    """
    保存 DataFrame 到用户指定的本地路径。
    """
    # 在侧边栏输入保存路径，默认路径为当前目录下的默认文件名
    save_path = st.sidebar.text_input(
        f"请输入保存路径（文件名） - {default_file_name}",
        value=f"./data/output/{default_file_name}",
        key=sidebar_key
    )

    if st.sidebar.button(f"保存 {default_file_name} 到本地", key=f"save_button_{sidebar_key}"):
        try:
            # 确保目标路径的文件夹存在
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            # 将 DataFrame 保存为 CSV 文件
            results_df.to_csv(save_path, index=False, encoding="utf-8-sig")
            st.sidebar.success(f"文件已成功保存到: {save_path}")
        except Exception as e:
            st.sidebar.error(f"保存文件时出错: {e}")

# 显示对话结果并提供保存功能
if "file_results" in st.session_state and st.session_state["file_results"]:
    st.write("### 自动对话结果")
    for file_name, results_df in st.session_state["file_results"].items():
        st.write(f"#### 文件: {file_name}")

        # 使用 st.data_editor 显示可编辑表格
        edited_df = st.data_editor(results_df, key=f"{file_name}_editor")

        # 如果用户编辑了表格，更新会话状态中的表格数据
        if not edited_df.equals(results_df):
            st.session_state["file_results"][file_name] = edited_df
            st.rerun()

        st.write("以下是编辑后的数据：")
        st.write(edited_df)

        # 提供保存到本地路径的功能（在侧边栏修改路径）
        save_to_local_path(edited_df, f"{file_name}_对话结果.csv", sidebar_key=f"{file_name}_save_path")
