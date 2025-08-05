import streamlit as st
import zipfile
import io
import os
from ebooklib import epub
from PIL import Image
from streamlit_sortables import sort_items

# --- 核心功能函数：创建EPUB ---
def create_epub(title, author, cover_image_bytes, chapters_data):
    """
    根据输入信息和章节数据创建EPUB文件。

    :param title: 书籍标题
    :param author: 作者
    :param cover_image_bytes: 封面图片的字节数据 (可以为 None)
    :param chapters_data: 一个包含 (文件名, 文件内容) 元组的列表
    :return: EPUB文件的字节数据
    """
    book = epub.EpubBook()

    # 设置元数据
    book.set_identifier('id123456') # 设置一个唯一的标识符
    book.set_title(title)
    book.set_language('zh') # 假设内容为中文
    book.add_author(author)

    # 处理封面
    if cover_image_bytes:
        cover_image = Image.open(io.BytesIO(cover_image_bytes))
        # 确保图片是RGB格式，有些PNG是RGBA
        if cover_image.mode == 'RGBA':
            cover_image = cover_image.convert('RGB')
        
        # 将PIL Image对象转换为字节流以供ebooklib使用
        img_byte_arr = io.BytesIO()
        cover_image.save(img_byte_arr, format='JPEG')
        cover_image_bytes_jpeg = img_byte_arr.getvalue()

        book.set_cover("cover.jpg", cover_image_bytes_jpeg)


    # 创建章节
    epub_chapters = []
    for i, (filename, content) in enumerate(chapters_data):
        # 从文件名中提取章节标题 (去掉.txt后缀)
        chapter_title = os.path.splitext(filename)[0]
        
        # 创建EpubHtml对象
        chapter = epub.EpubHtml(title=chapter_title, file_name=f'chap_{i+1}.xhtml', lang='zh')
        
        # 将纯文本内容转换为简单的HTML格式（保留换行）
        # 使用<p>标签包裹每一段
        html_content = f'<h1>{chapter_title}</h1>'
        paragraphs = content.split('\n')
        html_content += ''.join([f'<p>{p.strip()}</p>' for p in paragraphs if p.strip()])
        
        chapter.set_content(html_content)
        epub_chapters.append(chapter)
        book.add_item(chapter)

    # 定义书籍的阅读顺序（书脊）
    book.spine = ['nav'] + epub_chapters
    if 'cover' in book.items:
        book.spine.insert(0, 'cover')


    # 添加默认的导航文件 (NCX) 和目录
    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # 将EPUB文件写入内存中的字节流
    epub_bytes = io.BytesIO()
    epub.write_epub(epub_bytes, book, {})
    return epub_bytes.getvalue()

# --- Streamlit 界面布局 ---

st.set_page_config(layout="wide", page_title="TXT转EPUB转换器")

st.title("📚 TXT to EPUB 电子书转换器")
st.markdown("一个简单的小工具，可以帮助您将多个TXT文件合并并转换为一个EPUB格式的电子书。")

# 初始化Session State来存储文件数据
if 'txt_files' not in st.session_state:
    st.session_state.txt_files = {}

# --- 侧边栏：用于设置元数据和操作 ---
with st.sidebar:
    st.header("书籍元数据设置")
    book_title = st.text_input("书籍标题", "我的电子书")
    author_name = st.text_input("作者姓名", "佚名")
    cover_image_file = st.file_uploader("上传封面图片 (可选)", type=['png', 'jpg', 'jpeg'])
    
    cover_image_bytes = None
    if cover_image_file:
        cover_image_bytes = cover_image_file.getvalue()
        st.image(cover_image_bytes, caption="当前封面")
        
    st.info("设置好元数据后，请在主界面上传文件。")
    
    if st.button("清空所有已上传文件"):
        st.session_state.txt_files = {}
        st.rerun()


# --- 主界面 ---
st.header("1. 上传文件")
st.write("您可以直接上传多个TXT文件，或者上传一个包含所有TXT文件的ZIP压缩包。")

uploaded_files = st.file_uploader(
    "上传TXT文件或ZIP压缩包",
    type=['txt', 'zip'],
    accept_multiple_files=True,
    label_visibility="collapsed"
)

# 处理上传的文件
if uploaded_files:
    new_files_to_add = {}
    for uploaded_file in uploaded_files:
        # 如果是ZIP文件
        if uploaded_file.name.endswith('.zip'):
            with zipfile.ZipFile(io.BytesIO(uploaded_file.getvalue())) as z:
                for filename in z.namelist():
                    # 只处理TXT文件，并忽略Mac的元数据文件
                    if filename.endswith('.txt') and not filename.startswith('__MACOSX'):
                        # 使用 try-except 块来处理不同的编码
                        try:
                            content = z.read(filename).decode('utf-8')
                        except UnicodeDecodeError:
                            content = z.read(filename).decode('gbk', errors='ignore')
                        new_files_to_add[os.path.basename(filename)] = content
        # 如果是TXT文件
        elif uploaded_file.name.endswith('.txt'):
            try:
                content = uploaded_file.getvalue().decode('utf-8')
            except UnicodeDecodeError:
                content = uploaded_file.getvalue().decode('gbk', errors='ignore')
            new_files_to_add[uploaded_file.name] = content
    
    # 将新文件添加到session state中，并自动刷新界面
    if new_files_to_add:
        st.session_state.txt_files.update(new_files_to_add)
        st.rerun()


# --- 章节排序区 ---
if st.session_state.txt_files:
    st.header("2. 调整章节顺序 (可拖动)")
    st.info("请按住文件名并拖动，以调整它们在最终电子书中的顺序。")
    
    # 默认按文件名排序
    initial_order = sorted(st.session_state.txt_files.keys())
    
    # 使用 streamlit-sortables 实现拖动排序
    sorted_filenames = sort_items(initial_order, direction='vertical')
    
    # 将排序后的文件名和内容准备好
    chapters_to_process = [(name, st.session_state.txt_files[name]) for name in sorted_filenames]

    st.header("3. 生成并下载 EPUB")
    if st.button("✨ 点击生成EPUB文件", type="primary", use_container_width=True):
        if not book_title:
            st.error("书籍标题不能为空！")
        else:
            with st.spinner('正在合成电子书... 请稍候...'):
                try:
                    epub_file_bytes = create_epub(
                        title=book_title,
                        author=author_name,
                        cover_image_bytes=cover_image_bytes,
                        chapters_data=chapters_to_process
                    )
                    st.success("🎉 电子书生成成功！")
                    
                    # 提供下载按钮
                    st.download_button(
                        label="📥 下载EPUB文件",
                        data=epub_file_bytes,
                        file_name=f"{book_title}.epub",
                        mime="application/epub+zip",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"生成失败，出现错误：{e}")
else:
    st.warning("请先上传文件以开始操作。")