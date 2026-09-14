import pytest


@pytest.mark.parametrize('method,path', [
    ('GET', '/surveys'), ('GET', '/surveys/'),
    ('GET', '/recommendations'), ('GET', '/recommendations/'),
    ('POST', '/surveys'), ('POST', '/surveys/'),
    ('POST', '/chatbot'), ('POST', '/chatbot/'),
])
def test_collection_routes_authenticate_without_redirect(client, method, path):
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code == 401
    assert 'location' not in response.headers
    assert response.json()['detail'] == 'Not authenticated'


def test_signed_in_user_loads_lists_without_redirect(client):
    from tests.helpers import register_user, create_survey

    assert register_user(client).status_code == 201
    survey = create_survey(client)
    assert survey.status_code == 201
    response = client.get('/surveys', follow_redirects=False)
    assert response.status_code == 200
    assert response.json()[0]['id'] == survey.json()['id']
    response = client.get('/recommendations', follow_redirects=False)
    assert response.status_code == 200
    assert response.json() == []
