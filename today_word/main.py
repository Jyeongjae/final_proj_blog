# myapp/main.py
from dotenv import load_dotenv
import pandas as pd
from langchain.schema import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_teddynote.retrievers import KiwiBM25Retriever
from langchain_teddynote.retrievers import EnsembleRetriever, EnsembleMethod
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

import os
from django.conf import settings

# Load environment variables
load_dotenv()

# Load the CSV file and process it into LangChain Document objects
def load_csv_as_documents(file_path):
    df = pd.read_csv(file_path, encoding='utf-8')
    documents = []
    for i, row in df.iterrows():
        title = row['title'].strip() if pd.notna(row['title']) else ""
        content = row['content'].strip() if pd.notna(row['content']) else ""
        related_keyword = row['related_keyword'].strip() if pd.notna(row['related_keyword']) else ""
        
        combined_context = f"단어: {title}\n설명: {content}"
        
        doc = Document(
            page_content=combined_context,
            metadata={
                'title': title,
                'related_keyword': related_keyword,
                'doc_id': i
            }
        )
        documents.append(doc)
    return documents

# Setup FAISS and BM25 retrievers
file_path = os.path.join(settings.BASE_DIR, 'data', '700words.csv')
documents = load_csv_as_documents(file_path)
embeddings = OpenAIEmbeddings(model="text-embedding-3-large")

# FAISS Retriever
faiss_retriever = FAISS.from_documents(
    documents=documents, embedding=embeddings
).as_retriever(search_kwargs={"k": 3})

# KiwiBM25Retriever (Korean Morphological Analyzer + BM25 Algorithm)
bm25_retriever = KiwiBM25Retriever.from_documents(documents=documents, embedding=embeddings)
bm25_retriever.k = 3

# EnsembleRetriever with CC method for hybrid search
weights = [0.77, 0.23]
hybrid_retriever = EnsembleRetriever(
    retrievers=[faiss_retriever, bm25_retriever],
    weights=weights,
    method=EnsembleMethod.CC
)

# Define the prompt template
prompt_template = PromptTemplate(
    input_variables=["query", "retrieved_contents"],
    template="""
    당신의 역할은 경제 용어에 대해 친절하고 쉽게 이해할 수 있는 설명을 제공하는 것입니다.
    당신은 경제 지식이 없거나 경제 개념을 쉽게 배우고 싶은 사람들을 대상으로 '오늘의 단어' 포스팅을 작성합니다.
    
    먼저 단어의 정의를 상세하게 설명해 주고, 일상 생활에 적용할 수 있는 관련 예시를 하나 간단하게 들어주세요.
    
    마지막으로 이 용어를 이해하는 것이 왜 중요한지 요약하고 글을 마무리해 주세요.
    경제 지식이 전혀 없는 사람도 쉽게 이해하고 흥미롭게 읽을 수 있도록 친근하고 쉽게 작성해 주세요.
    
    # 주의사항:
    1. 문서의 내용을 기반으로만 글을 작성하세요. 내용을 지어내거나 사실과 다르게 작성하지 마세요.
    2. 만약 설명할 수 없는 부분이 있다면, '모르겠습니다'라고 답하세요.
    3. 모든 제목은 #나 ## 같은 Markdown 표시 없이 굵은 글씨(**)로 나타나야 합니다. 예를 들어'## 경기는'는 '**경기**는'로 표시합니다.
    4. 본문에는 일반 텍스트 형식을 사용하고, 필요할 경우 단어에만 굵은 글씨를 사용해주세요.
    5. 제목을 제외하여 주세요.
    
    이제 주제에 맞게 블로그 글을 작성해 주세요.
    질문: {query}
    단락: {retrieved_contents}
    답변:
"""
)

llm = ChatOpenAI(model="gpt-4o", temperature=0.8)
chain = prompt_template | llm

# Function to get response from LLM chain
def generate_response(query):
    retrieved_documents = hybrid_retriever.invoke(query)
    retrieved_contents = "\n".join([doc.page_content for doc in retrieved_documents])
    response = chain.invoke({"query": query, "retrieved_contents": retrieved_contents})
    return response