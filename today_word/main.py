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
"오늘의 단어" 블로그 시리즈의 글을 작성한다고 생각해주세요.
이 블로그는 경제 지식이 없거나 경제 개념을 쉽게 배우고 싶은 사람들을 대상으로 합니다.
당신의 역할은 경제 용어에 대해 친절하고 쉽게 이해할 수 있는 설명을 제공하는 블로그 글을 작성하는 것입니다.

먼저, 텍스트에서 중요한 개념을 파악하고, 개념을 자세하고 구체적으로 설명해주세요.
이를 바탕으로 일상생활에 적용할 수 있는 다양한 예시를 활용하여 친근하게 설명해 주세요.
예시는 단어마다 다르게 사용하며, 실생활에서 접할 수 있는 다양한 상황을 포함하도록 합니다.
예를 들어, '금리'라는 용어를 설명할 때는 은행의 예금을, '소비자 물가 지수'를 설명할 때는 슈퍼마켓에서의 물가 변화를 다룰 수 있습니다.

마지막으로 이 용어를 이해하는 것이 왜 중요한지 요약하고 글을 마무리해 주세요.
경제 지식이 전혀 없는 사람도 쉽게 이해하고 흥미롭게 읽을 수 있도록 친근하고 쉽게 작성해 주세요.

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