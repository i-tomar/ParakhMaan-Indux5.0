from tests.helpers import anonymous_client, client_for

def test_health_endpoint():
    response = anonymous_client().get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Legal Metrology" in data["service"]

def test_auth_login():
    client = anonymous_client()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "operator@parakhmaan.local", "password": "ParakhMaan@2026"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == "operator@parakhmaan.local"
    assert data["user"]["role"] == "OPERATOR"

def test_inspection_crud_and_demo():
    client = client_for("ADMIN")
    # 1. Test Seed Demo data
    seed_res = client.post("/api/v1/demo/seed")
    assert seed_res.status_code == 200

    # 2. Test List Inspections
    list_res = client.get("/api/v1/inspections")
    assert list_res.status_code == 200
    inspections = list_res.json()
    assert len(inspections) >= 1

    # 3. Test Get Detail
    insp_id = inspections[0]["id"]
    detail_res = client.get(f"/api/v1/inspections/{insp_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "inspection_number" in detail

    # 4. Test Dashboard summary
    dash_res = client.get("/api/v1/dashboard/summary")
    assert dash_res.status_code == 200
    dash_data = dash_res.json()
    assert dash_data["total_inspections"] >= 1
