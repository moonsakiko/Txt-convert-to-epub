import streamlit as st
import zipfile
import io
import os
import re
from ebooklib import epub
from PIL import Image
from streamlit_sortables import sort_items

# --- Session State 初始化 ---
# 使用 st.session_state 来存储跨页面刷新的数据
if 'txt_files' not in st.session_state:
    st.session_state.txt_files = {}  # 存储 {文件名: 内容}
if 'epub_file_bytes' not in st.session_state:
    st.session_state.epub_file_bytes = None  # 存储生成好的EPUB文件字节

# --- 核心功能函数 ---
def sanitize_filename(filename):
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def create_epub(title, author, description, cover_image_bytes, chapters_data):
    """根据输入信息和章节数据创建EPUB文件"""
    book = epub.EpubBook()

    # 设置元数据
    book.set_identifier(f'urn:uuid:{title}-{author}')
    book.set_title(title)
    book.set_language('zh')
    book.add_author(author)
    if description:
        book.add_metadata('DC', 'description', description)

    # 处理封面
    if cover_image_bytes:
        try:
            img_pil = Image.open(io.BytesIO(cover_image_bytes))
            if img_pil.mode == 'RGBA':
                img_pil = img_pil.convert('RGB')
            
            img_byte_arr = io.BytesIO()
            img_pil.save(img_byte_arr, format='JPEG')
            cover_image_content = img_byte_arr.getvalue()
            
            book.set_cover("cover.jpg", cover_image_content)
        except Exception as e:
            st.warning(f"封面图片处理失败，已跳过。错误: {e}")

    # 创建章节内容
    epub_chapters = []
    for i, (filename, content) in enumerate(chapters_data):
        chapter_title = os.path.splitext(filename)[0]
        chapter = epub.EpubHtml(title=chapter_title, file_name=f'chap_{i+1}.xhtml', lang='zh')
        
        # 将纯文本转换为保留换行的HTML
        html_content = f'<h1>{chapter_title}</h1>'
        paragraphs = content.split('\n')
        html_content += ''.join([f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()])
        
        chapter.set_content(html_content)
        epub_chapters.append(chapter)
        book.add_item(chapter)

    # 定义书籍的阅读顺序（书脊）
    book.spine = ['nav'] + epub_chapters
    # Ebooklib 自动处理封面顺序，无需手动插入
    
    # 添加目录
    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # 写入内存
    epub_bytes = io.BytesIO()
    epub.write_epub(epub_bytes, book, {})
    return epub_bytes.getvalue()

# --- Streamlit 界面 ---

st.set_page_config(layout="wide", page_title="TXT转EPUB转换器")

st.title("📚 TXT to EPUB 电子书转换器 (优化版)")
st.markdown("上传TXT文件或ZIP包，拖动排序，一键生成EPUB电子书。")

# --- 回调函数：当输入改变时，清空已生成的EPUB ---
def clear_generated_epub():
    st.session_state.epub_file_bytes = None

# --- 侧边栏 ---
with st.sidebar:
    st.header("书籍元数据设置")
    
    book_title = st.text_input(
        "书籍标题", "我的电子书", 
        on_change=clear_generated_epub
    )
    author_name = st.text_input(
        "作者姓名", "佚名",
        on_change=clear_generated_epub
    )
    book_description = st.text_area(
        "书籍简介 (可选)",
        placeholder="在这里输入书籍的简介...",
        on_change=clear_generated_epub
    )
    
    cover_image_file = st.file_uploader(
        "上传封面图片 (可选)", 
        type=['png', 'jpg', 'jpeg'],
        on_change=clear_generated_epub
    )
    
    cover_image_bytes = None
    if cover_image_file:
        cover_image_bytes = cover_image_file.getvalue()
        st.image(cover_image_bytes, caption="当前封面")
        
    if st.button("清空所有已上传文件"):
        st.session_state.txt_files = {}
        clear_generated_epub()
        st.rerun()

# --- 主界面 ---
st.header("1. 上传文件")
st.write("支持同时上传多个TXT文件，或一个包含所有TXT文件的ZIP压缩包。")

uploaded_files = st.file_uploader(
    "上传文件区域",
    type=['txt', 'zip'],
    accept_multiple_files=True,
    label_visibility="collapsed",
    on_change=clear_generated_epub # 上传新文件也清空旧的生成结果
)

# 处理上传的文件
if uploaded_files:
    with st.spinner('正在处理上传的文件...'):
        new_files_to_add = {}
        for uploaded_file in uploaded_files:
            if uploaded_file.name.endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(uploaded_file.getvalue())) as z:
                    for filename in sorted(z.namelist()): # 默认按压缩包内文件名排序
                        if filename.endswith('.txt') and not filename.startswith('__MACOSX'):
                            try:
                                content = z.read(filename).decode('utf-8')
                            except UnicodeDecodeError:
                                content = z.read(filename).decode('gbk', errors='ignore')
                            new_files_to_add[os.path.basename(filename)] = content
            elif uploaded_file.name.endswith('.txt'):
                try:
                    content = uploaded_file.getvalue().decode('utf-8')
                except UnicodeDecodeError:
                    content = uploaded_file.getvalue().decode('gbk', errors='ignore')
                new_files_to_add[uploaded_file.name] = content
        
        # 更新文件列表
        st.session_state.txt_files.update(new_files_to_add)

# --- 章节排序和生成区域 ---
if st.session_state.txt_files:
    col1, col2 = st.columns(2)

    with col1:
        st.header("2. 调整章节顺序")
        st.info("按住文件名并拖动以排序。")
        
        initial_order = sorted(st.session_state.txt_files.keys())
        sorted_filenames = sort_items(initial_order, direction='vertical')
        
        chapters_to_process = [(name, st.session_state.txt_files[name]) for name in sorted_filenames]

    with col2:
        st.header("3. 生成并下载")
        st.info("完成排序后，点击下方按钮生成电子书。")

        if st.button("✨ 点击生成EPUB", type="primary", use_container_width=True):
            if not book_title:
                st.error("书籍标题不能为空！")
            elif not chapters_to_process:
                st.error("没有可用的章节文件！")
            else:
                with st.spinner('正在合成电子书，请稍候...'):
                    try:
                        epub_bytes = create_epub(
                            title=book_title,
                            author=author_name,
                            description=book_description,
                            cover_image_bytes=cover_image_bytes,
                            chapters_data=chapters_to_process
                        )
                        st.session_state.epub_file_bytes = epub_bytes # 保存到session state
                        st.success("🎉 电子书生成成功！下载按钮已出现。")
                    except Exception as e:
                        st.error(f"生成失败，出现错误：{e}")
                        st.session_state.epub_file_bytes = None

        # 只有当EPUB文件成功生成后，才显示下载按钮
        if st.session_state.epub_file_bytes:
            safe_book_title = sanitize_filename(book_title)
            st.download_button(
                label="📥 下载EPUB文件",
                data=st.session_state.epub_file_bytes,
                file_name=f"{safe_book_title}.epub",
                mime="application/epub+zip",
                use_container_width=True
            )
else:
    st.warning("请先上传文件以开始操作。")
