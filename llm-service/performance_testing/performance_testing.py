#
#  CLOUDERA APPLIED MACHINE LEARNING PROTOTYPE (AMP)
#  (C) Cloudera, Inc. 2024
#  All rights reserved.
#
#  Applicable Open Source License: Apache 2.0
#
#  NOTE: Cloudera open source products are modular software products
#  made up of hundreds of individual components, each of which was
#  individually copyrighted.  Each Cloudera open source product is a
#  collective work under U.S. Copyright Law. Your license to use the
#  collective work is as provided in your written agreement with
#  Cloudera.  Used apart from the collective work, this file is
#  licensed for your use pursuant to the open source license
#  identified above.
#
#  This code is provided to you pursuant a written agreement with
#  (i) Cloudera, Inc. or (ii) a third-party authorized to distribute
#  this code. If you do not have a written agreement with Cloudera nor
#  with an authorized and properly licensed third party, you do not
#  have any rights to access nor to use this code.
#
#  Absent a written agreement with Cloudera, Inc. ("Cloudera") to the
#  contrary, A) CLOUDERA PROVIDES THIS CODE TO YOU WITHOUT WARRANTIES OF ANY
#  KIND; (B) CLOUDERA DISCLAIMS ANY AND ALL EXPRESS AND IMPLIED
#  WARRANTIES WITH RESPECT TO THIS CODE, INCLUDING BUT NOT LIMITED TO
#  IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY AND
#  FITNESS FOR A PARTICULAR PURPOSE; (C) CLOUDERA IS NOT LIABLE TO YOU,
#  AND WILL NOT DEFEND, INDEMNIFY, NOR HOLD YOU HARMLESS FOR ANY CLAIMS
#  ARISING FROM OR RELATED TO THE CODE; AND (D)WITH RESPECT TO YOUR EXERCISE
#  OF ANY RIGHTS GRANTED TO YOU FOR THE CODE, CLOUDERA IS NOT LIABLE FOR ANY
#  DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, PUNITIVE OR
#  CONSEQUENTIAL DAMAGES INCLUDING, BUT NOT LIMITED TO, DAMAGES
#  RELATED TO LOST REVENUE, LOST PROFITS, LOSS OF INCOME, LOSS OF
#  BUSINESS ADVANTAGE OR UNAVAILABILITY, OR LOSS OR CORRUPTION OF
#  DATA.
#

#
#  CLOUDERA APPLIED MACHINE LEARNING PROTOTYPE (AMP)
#  (C) Cloudera, Inc. 2024
#  All rights reserved.
#
#  Applicable Open Source License: Apache 2.0
#
#
#  This code is provided to you pursuant a written agreement with
#  (i) Cloudera, Inc. or (ii) a third-party authorized to distribute
#  this code. If you do not have a written agreement with Cloudera nor
#  with an authorized and properly licensed third party, you do not
#  have any rights to access nor to use this code.
#
#  Absent a written agreement with Cloudera, Inc. ("Cloudera") to the
#  contrary, A) CLOUDERA PROVIDES THIS CODE TO YOU WITHOUT WARRANTIES OF ANY
#  KIND; (B) CLOUDERA DISCLAIMS ANY AND ALL EXPRESS AND IMPLIED
#  WARRANTIES WITH RESPECT TO THIS CODE, INCLUDING BUT NOT LIMITED TO
#  IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY AND
#  FITNESS FOR A PARTICULAR PURPOSE; (C) CLOUDERA IS NOT LIABLE TO YOU,
#  AND WILL NOT DEFEND, INDEMNIFY, NOR HOLD YOU HARMLESS FOR ANY CLAIMS
#  ARISING FROM OR RELATED TO THE CODE; AND (D)WITH RESPECT TO YOUR EXERCISE
#  OF ANY RIGHTS GRANTED TO YOU FOR THE CODE, CLOUDERA IS NOT LIABLE FOR ANY
#  DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, PUNITIVE OR
#  CONSEQUENTIAL DAMAGES INCLUDING, BUT NOT LIMITED TO, DAMAGES
#  RELATED TO LOST REVENUE, LOST PROFITS, LOSS OF INCOME, LOSS OF
#  BUSINESS ADVANTAGE OR UNAVAILABILITY, OR LOSS OR CORRUPTION OF
#  DATA.
#
import os
import sys
import time

import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llama_index.core import VectorStoreIndex
from llama_index.core.indices.vector_store import VectorIndexRetriever
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.query_engine import RetrieverQueryEngine

from app.ai.vector_stores.qdrant import QdrantVectorStore
from app.rag_types import RagPredictConfiguration
from app.services import models
from app.services.querier import FlexibleChatEngine, CUSTOM_PROMPT


# usage: uv run --env-file=../.env performance_testing/performance_testing.py <data_source_id> questions_mini.csv
def main():
    data_source_id: int = int(sys.argv[1])
    file: str = sys.argv[2]
    with open(os.path.abspath(os.path.join(os.path.dirname(__file__), file)), "r") as f:
        df = pd.read_csv(f)
        questions: list[str] = df["Question"].tolist()

    with open(os.path.abspath(os.path.join(os.path.dirname(__file__), "raw_results.csv")), "a") as details:
        for hyde in [True, False]:
            for condensing in [False]:
                print(f"Running with hyde={hyde}")
                score_sum = 0
                score_count = 0
                max_score = 0
                chat_engine = setup(use_question_condensing=condensing, use_hyde=hyde, data_source_id=data_source_id)
                for question in questions:
                    nodes = chat_engine.retrieve(message=question, chat_history=None)
                    if nodes:
                        max_score = max(max_score, max(node.score for node in nodes))
                        avg_score = sum(node.score for node in nodes) / len(nodes)
                        score_sum += avg_score
                        score_count += 1
                        for index, node in enumerate(nodes):
                            # timestamp,hyde,score,chunk_no,question
                            details.write(f'{time.time()},{hyde},{node.score},{node.metadata.get("file_name")},{node.node_id}{index + 1},"{question}"\n')
                    details.flush()

                average_score = score_sum / score_count
                print(f"{chat_engine.configuration=}")
                print(f"Average score: {average_score}")
                with open(os.path.abspath(os.path.join(os.path.dirname(__file__), "results.csv")), "a") as f:
                    f.write(f"{hyde},{max_score},{average_score}\n")
                    f.flush()


def setup(data_source_id: int, use_question_condensing=True, use_hyde=True):
    configuration = RagPredictConfiguration(use_question_condensing=use_question_condensing, top_k=5,
                                            model_name="meta.llama3-1-8b-instruct-v1:0",
                                            use_hyde=use_hyde)
    llm = models.get_llm(model_name=configuration.model_name)
    response_synthesizer = get_response_synthesizer(llm=llm)
    qdrant_store = QdrantVectorStore.for_chunks(data_source_id)
    vector_store = qdrant_store.llama_vector_store()
    embedding_model = qdrant_store.get_embedding_model()
    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        embed_model=embedding_model,
    )
    retriever = VectorIndexRetriever(
        index=index,
        similarity_top_k=configuration.top_k,
        embed_model=embedding_model,  # is this needed, really, if it's in the index?
    )
    query_engine = RetrieverQueryEngine(
        retriever=retriever, response_synthesizer=response_synthesizer
    )
    chat_engine = FlexibleChatEngine.from_defaults(query_engine=query_engine, llm=llm,
                                                   condense_question_prompt=CUSTOM_PROMPT)
    chat_engine.configuration = configuration
    return chat_engine


if __name__ == "__main__":
    for _ in range(3):
        main()
