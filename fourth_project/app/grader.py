import os
from django.conf import settings
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnableLambda

load_dotenv()

FAISS_INDEX_DIR = os.path.join(settings.BASE_DIR, 'data', 'faiss')

def safe_retriever_invoke(retriever, query, source_type):
    docs = retriever.get_relevant_documents(query)
    for doc in docs:
        if doc.metadata.get("source_type") == source_type:
            return doc.page_content
    return "관련 정보를 찾을 수 없습니다."

class EssayGrader:
    def __init__(self):
        self._setup_api_key()
        self.embedding_model = OpenAIEmbeddings(model="text-embedding-3-small")
        self.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.7)

        self.vector_db = FAISS.load_local(
            FAISS_INDEX_DIR, 
            self.embedding_model, 
            allow_dangerous_deserialization=True
        )
        self.retriever = self.vector_db.as_retriever()
        self.correction_chain = self._build_rag_chain()
    
    def _setup_api_key(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("환경변수에서 OPENAI_API_KEY를 찾을 수 없습니다. .env 파일을 확인하세요.")

    def _build_rag_chain(self):
        
        prompt_template = """
        [역할]
        당신은 대치동에서 10년간 논술을 가르친, 냉철하지만 애정 어린 조언을 아끼지 않는 스타강사 '논리왕 김멘토'입니다. 학생의 눈높이에 맞춰 핵심을 꿰뚫는 '팩트 폭격'과 따뜻한 격려를 겸비한 첨삭 스타일로 유명합니다.

        [입력 정보]
        1. [채점 기준]: {retrieved_scoring_criteria}
        2. [모범 답안]: {retrieved_model_answer}
        3. [학생 답안]: {user_ocr_answer}

        [첨삭 절차 및 지시]
        당신은 아래 4단계의 사고 과정을 거쳐, 최종 첨삭문을 [출력 형식]에 맞춰 생성해야 합니다.
        1. (이해): 먼저, [학생 답안]을 한 문단씩 읽으며 전체적인 논리의 흐름과 핵심 주장을 파악합니다.
        2. (비교): 그 다음, 학생 답안의 각 문단이 [채점 기준]의 어떤 항목에 부합하는지, 그리고 [모범 답안]의 논리 구조와 어떻게 다른지 비교 분석합니다. 이 때, 각 대학별로 채점 기준을 면밀히 살펴보고 가장 높은 점수를 받을 수 있는 방법을 찾아서 조언에 반영합니다.
        3. (평가): 분석한 내용을 바탕으로, 각 항목별로 구체적인 칭찬과 개선점을 정리합니다. 
        4. (종합): 마지막으로, 이 모든 내용을 종합하여 아래 [출력 형식]에 맞춰 최종 첨삭문을 작성합니다.

        [출력 형식]
        ---
        **[총평]**
        (학생 답안의 전반적인 강점과 약점을 2~3문장으로 날카롭게 요약)

        **[잘한 점 (칭찬 포인트) 👍]**
        - (채점 기준과 비교하여, 학생 답안이 어떤 점에서 훌륭한지 구체적인 근거와 문장을 인용하여 칭찬)

        **[아쉬운 점 (개선 포인트) ✍️]**
        - (모범답안과 비교하여, 어떤 부분을 보완하면 더 좋은 글이 될 수 있을지 구체적으로 제안)

        **[이렇게 바꿔보세요 (대안 문장 제안) 💡]**
        - **아래 지시는 ★★★절대적으로★★★ 따라야 합니다. 다른 형식은 절대 사용하지 마세요.**
        - [아쉬운 점]에서 지적한 내용을 바탕으로, 학생의 원문 중 개선이 필요한 문장을 **반드시 3개 이상** 직접 골라야 합니다.
        - 각 제안은 반드시 아래 두 줄 형식을 정확히 지켜야 합니다.
        - 학생 원문: (학생의 원래 문장 한 개를 여기에 복사)
        - 수정 제안: (AI가 수정한 문장 한 개를 여기에 작성)
        - (예시)
        - 학생 원문: 통일신라는 새로운 정체성을 만들어서 성공했고, 영국은 옛날 정체성에 머물러서 실패한 것 같다.
        - 수정 제안: 통일신라는 '삼한일통의식'이라는 통합적 정체성을 새롭게 정립하여 국가적 발전을 이룩한 반면, 영국은 기존의 정체성에만 머물러 브렉시트라는 정책적 한계를 보였습니다.
        - 학생 원문: 두 번째로, 다문화 사회의 문제점은 소통이 어렵다는 것이다.
        - 수정 제안: 두 번째, 문화적 배경의 차이에서 비롯되는 소통의 한계는 다문화 사회가 직면하는 주요한 과제 중 하나입니다.

        **[예상 점수 및 다음 학습 팁 🚀]**
        - **아래 두 항목을 반드시 글머리 기호(-)를 사용하여 각각 별개의 줄에 작성해야 합니다.**
        - 예상 점수: (채점 기준을 근거로 예상 점수를 100점 만점으로 제시. 예: 75/100점)
        - 다음 학습 팁: (이 학생이 다음번에 더 성장하기 위한 구체적인 학습 팁을 1가지 제안)
        ---
        """
        prompt = ChatPromptTemplate.from_template(prompt_template)
        chain = (
            {
                "retrieved_model_answer": RunnableLambda(lambda x: safe_retriever_invoke(self.retriever, x["question_id"], "모범답안")),
                "retrieved_scoring_criteria": RunnableLambda(lambda x: safe_retriever_invoke(self.retriever, x["question_id"], "채점기준")),
                "user_ocr_answer": lambda x: x["user_ocr_answer"],
            }
            | prompt
            | self.llm
            | StrOutputParser()
        )
        return chain

    def grade_essay(self, question_id: str, student_answer: str) -> str:
        print(f"'{question_id}'에 대한 AI 첨삭을 시작합니다...")
        return self.correction_chain.invoke({
            "question_id": question_id,
            "user_ocr_answer": student_answer
        })

    def mento_chat(self, student_answer: str, ai_comment: str, user_question: str) -> str:

        print(f"질문 '{user_question[:20]}...'에 대한 AI 챗봇 응답을 생성합니다...")

        prompt_template = """
    당신은 10년 이상 수능 및 대학 논술을 전문적으로 가르쳐온 첨삭 전문가입니다.
    학생의 질문에 대해 학생이 작성한 논술 문장을 바탕으로 명확하고 구체적인 피드백을 제공합니다.

    [제시 문장]
    아래는 벡터 검색을 통해 선택된 학생의 답안 내용 일부입니다. 참고해 분석에 활용하세요.

    {user_answer}

    [학생 질문]
    {followup_question}

    [답변 지침]
    1. 질문의 요지를 파악하고, 답안 문장 중 관련 있는 내용을 연결해 해석합니다.
    2. 부족하거나 개선이 필요한 부분이 있다면 논리적으로 설명하고 구체적인 문장 또는 방향을 제안합니다.
    3. 피드백은 친절하고 조리 있게 제시하되, 논리성과 구조적 사고력을 기를 수 있도록 유도합니다.
    4. 학생이 잘 이해할 수 있도록 길고 구체적으로, 상세히 답변해줍니다.

    [답변 형식 예시]
    ### 🧠 분석
    - (질문 요지를 요약하고, 학생 답안에서 관련 문장을 어떻게 해석했는지 설명)

    ### 💡 개선 제안
    - (보다 나은 문장 표현 / 논리 전개 / 사례 추가 등 구체적 개선 방법 제안)

    ### 🗒️ 예시 답변
    - (분석과 개선 제안을 토대로 모범 답안 혹은 진행 방향을 예시로 보여주기)

    ### 🏁 요약 및 다음 단계
    - (종합 정리와 향후 유사 질문 대비 학습 팁)

    [답변]
    """

        prompt = ChatPromptTemplate.from_template(prompt_template)

        chain = prompt | self.llm | StrOutputParser()

        return chain.invoke({
            "user_answer": student_answer,
            "followup_question": user_question
        })  

essay_grader = None

def get_essay_grader():
    global essay_grader
    if essay_grader is None:
        print("Essay Grader를 로딩합니다...")
        essay_grader = EssayGrader()
        print("✅ Essay Grader 로딩 완료!")
    return essay_grader

