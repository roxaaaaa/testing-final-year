import server as server_module


def test_generate_questions_no_authorization_header(client, monkeypatch):
    monkeypatch.setattr(
        server_module.QuestionGenerator,
        "generate_questions",
        lambda self: ["Sample question one?", "Sample question two?", "Sample question three?"],
    )

    r = client.post(
        "/api/ai/generate_questions",
        json={"topic_name": "Soils", "level": "ordinary", "persona": "student"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert len(body["questions"]) == 3
    assert body["count"] == 3
    assert "exam_id" not in body
    assert "generations_remaining" not in body


def test_generate_questions_teacher_persona_five_questions(client, monkeypatch):
    monkeypatch.setattr(
        server_module.QuestionGenerator,
        "generate_questions",
        lambda self: [f"Q{i}?" for i in range(5)],
    )

    r = client.post(
        "/api/ai/generate_questions",
        json={"topic_name": "Crops", "level": "higher", "persona": "teacher"},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 5
