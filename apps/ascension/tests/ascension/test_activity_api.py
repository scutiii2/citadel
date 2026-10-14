from tests.ascension.test_api import client, clock, headers, start_profile


def test_activity_choices_and_claim_are_server_authoritative(client, clock):
    start_profile(client)
    auth = headers(client)
    definitions = client.get('/ascension/activities', headers=auth).json()
    assert len(definitions['hunts']) == 3 and len(definitions['trial_types']) == 6
    preview = client.get('/ascension/activities/hunts/outskirts/prepare?ascended_id=guardian', headers=auth).json()
    assert preview['overall'] == 185 and preview['penalty_percent'] == 0
    assert client.post('/ascension/expeditions', headers=headers(client), json={'ascended_id':'guardian', 'duration_hours':True}).status_code == 400
    assert client.post('/ascension/expeditions', headers=headers(client), json={'ascended_id':'guardian', 'duration_hours':2, 'xp_reward':999}).status_code == 400
    departed = client.post('/ascension/expeditions', headers=headers(client), json={'ascended_id':'guardian', 'duration_hours':2})
    assert departed.status_code == 201
    exp = departed.json()['expedition']
    assert client.post(f"/ascension/expeditions/{exp['id']}/claim", headers=headers(client)).status_code == 409
    assert client.put('/ascension/squad', headers=headers(client), json={'ascended_ids':['guardian']}).status_code == 409
    assert client.post(f"/ascension/expeditions/{exp['id']}/claim", headers=headers(client, owner='bob')).status_code == 404
    clock.t = exp['ends_at']
    first = client.post(f"/ascension/expeditions/{exp['id']}/claim", headers=headers(client)).json()
    assert first['xp'] == 200 and first['insignia'] == 50
    assert client.post(f"/ascension/expeditions/{exp['id']}/claim", headers=headers(client)).json() == first


def test_trial_preparation_and_strict_choices(client):
    start_profile(client)
    auth = headers(client)
    empty = client.get('/ascension/trials/pure/stages/1/prepare', headers=auth).json()
    assert empty['eligible_ascended_ids'] == [] and empty['reason'] == 'No eligible Ascended'
    assert client.get('/ascension/trials', headers=auth).status_code == 200
    assert client.post('/ascension/trials/enchant/stages/2/battles', headers=headers(client), json={'ascended_id':'guardian'}).status_code == 400
    result = client.post('/ascension/trials/enchant/stages/1/battles', headers=headers(client), json={'ascended_id':'guardian', 'preset_slot':1, 'mode':'autonomous'})
    assert result.status_code == 201
    assert result.json()['activity']['kind'] == 'trial'
    assert 'catch' not in {a['kind'] for a in result.json()['actions']}
