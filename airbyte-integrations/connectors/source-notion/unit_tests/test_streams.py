#
# Copyright (c) 2023 Airbyte, Inc., all rights reserved.
#

import random
from http import HTTPStatus
from unittest.mock import MagicMock, patch

import pytest
import logging
import requests
from airbyte_cdk.models import SyncMode
from source_notion.streams import Blocks, NotionStream, Users, Pages


@pytest.fixture
def patch_base_class(mocker):
    # Mock abstract methods to enable instantiating abstract class
    mocker.patch.object(NotionStream, "path", "v0/example_endpoint")
    mocker.patch.object(NotionStream, "primary_key", "test_primary_key")
    mocker.patch.object(NotionStream, "__abstractmethods__", set())


def test_request_params(patch_base_class):
    stream = NotionStream(config=MagicMock())
    inputs = {"stream_slice": None, "stream_state": None, "next_page_token": None}
    expected_params = {}
    assert stream.request_params(**inputs) == expected_params


def test_next_page_token(patch_base_class, requests_mock):
    stream = NotionStream(config=MagicMock())
    requests_mock.get("https://dummy", json={"next_cursor": "aaa"})
    inputs = {"response": requests.get("https://dummy")}
    expected_token = {"next_cursor": "aaa"}
    assert stream.next_page_token(**inputs) == expected_token


@pytest.mark.parametrize('response_json, expected_output', [
    ({'next_cursor': 'some_cursor', 'has_more': True}, {'next_cursor': 'some_cursor'}),
    ({'has_more': False}, None),
    ({}, None)
])
def test_next_page_token_with_no_cursor(patch_base_class, response_json, expected_output):
    stream = NotionStream(config=MagicMock())
    mock_response = MagicMock()
    mock_response.json.return_value = response_json
    result = stream.next_page_token(mock_response)
    assert result == expected_output


def test_parse_response(patch_base_class, requests_mock):
    stream = NotionStream(config=MagicMock())
    requests_mock.get("https://dummy", json={"results": [{"a": 123}, {"b": "xx"}]})
    resp = requests.get("https://dummy")
    inputs = {"response": resp, "stream_state": MagicMock()}
    expected_parsed_object = [{"a": 123}, {"b": "xx"}]
    assert list(stream.parse_response(**inputs)) == expected_parsed_object


def test_request_headers(patch_base_class):
    stream = NotionStream(config=MagicMock())
    inputs = {"stream_slice": None, "stream_state": None, "next_page_token": None}
    expected_headers = {"Notion-Version": "2022-06-28"}
    assert stream.request_headers(**inputs) == expected_headers


def test_http_method(patch_base_class):
    stream = NotionStream(config=MagicMock())
    expected_method = "GET"
    assert stream.http_method == expected_method


@pytest.mark.parametrize(
    ("http_status", "should_retry"),
    [
        (HTTPStatus.OK, False),
        (HTTPStatus.BAD_REQUEST, True),
        (HTTPStatus.TOO_MANY_REQUESTS, True),
        (HTTPStatus.INTERNAL_SERVER_ERROR, True),
    ],
)
def test_should_retry(patch_base_class, http_status, should_retry):
    response_mock = MagicMock()
    response_mock.status_code = http_status
    stream = NotionStream(config=MagicMock())
    assert stream.should_retry(response_mock) == should_retry


def test_should_not_retry_with_ai_block(requests_mock):
    stream = Blocks(parent=None, config=MagicMock())
    json_response = {
        "object":"error",
        "status":400,
        "code":"validation_error",
        "message":"Block type ai_block is not supported via the API.",
    }
    requests_mock.get("https://api.notion.com/v1/blocks/123", json=json_response, status_code=400)
    test_response = requests.get("https://api.notion.com/v1/blocks/123")
    assert not stream.should_retry(test_response)


def test_should_not_retry_with_not_found_block(requests_mock):
    stream = Blocks(parent=None, config=MagicMock())
    json_response = {
        "object": "error",
        "status": 404,
        "message": "Not Found for url: https://api.notion.com/v1/blocks/123/children?page_size=100",
    }
    requests_mock.get("https://api.notion.com/v1/blocks/123", json=json_response, status_code=404)
    test_response = requests.get("https://api.notion.com/v1/blocks/123")
    assert not stream.should_retry(test_response)


def test_empty_blocks_results(requests_mock):
    stream = Blocks(parent=None, config=MagicMock())
    requests_mock.get(
        "https://api.notion.com/v1/blocks/aaa/children",
        json={
            "next_cursor": None,
        },
    )
    stream.block_id_stack = ["aaa"]
    assert list(stream.read_records(sync_mode=SyncMode.incremental, stream_slice=[])) == []


def test_backoff_time(patch_base_class):
    response_mock = MagicMock(headers={"retry-after": "10"})
    stream = NotionStream(config=MagicMock())
    assert stream.backoff_time(response_mock) == 10.0


def test_users_request_params(patch_base_class):
    stream = Users(config=MagicMock())

    # No next_page_token. First pull
    inputs = {"stream_slice": None, "stream_state": None, "next_page_token": None}
    expected_params = {"page_size": 100}
    assert stream.request_params(**inputs) == expected_params

    # When getting pages after the first pull.
    inputs = {"stream_slice": None, "stream_state": None, "next_page_token": {"next_cursor": "123"}}
    expected_params = {"start_cursor": "123", "page_size": 100}
    assert stream.request_params(**inputs) == expected_params


def test_user_stream_handles_pagination_correctly(requests_mock):
    """
    Test shows that Users stream uses pagination as per Notion API docs.
    """

    response_body = {
        "object": "list",
        "results": [{"id": f"{x}", "object": "user", "type": ["person", "bot"][random.randint(0, 1)]} for x in range(100)],
        "next_cursor": "bc48234b-77b2-41a6-95a3-6a8abb7887d5",
        "has_more": True,
        "type": "user",
    }
    requests_mock.get("https://api.notion.com/v1/users?page_size=100", json=response_body)

    response_body = {
        "object": "list",
        "results": [{"id": f"{x}", "object": "user", "type": ["person", "bot"][random.randint(0, 1)]} for x in range(100, 200)],
        "next_cursor": "67030467-b97b-4729-8fd6-2fb33d012da4",
        "has_more": True,
        "type": "user",
    }
    requests_mock.get("https://api.notion.com/v1/users?page_size=100&start_cursor=bc48234b-77b2-41a6-95a3-6a8abb7887d5", json=response_body)

    response_body = {
        "object": "list",
        "results": [{"id": f"{x}", "object": "user", "type": ["person", "bot"][random.randint(0, 1)]} for x in range(200, 220)],
        "next_cursor": None,
        "has_more": False,
        "type": "user",
    }
    requests_mock.get("https://api.notion.com/v1/users?page_size=100&start_cursor=67030467-b97b-4729-8fd6-2fb33d012da4", json=response_body)

    stream = Users(config=MagicMock())

    records = stream.read_records(sync_mode=SyncMode.full_refresh)
    records_length = sum(1 for _ in records)
    assert records_length == 220


@pytest.mark.parametrize("stream,parent,status_code,expected_availability,expected_reason_substring", [
    (Users, None, 403, False, "This is likely due to insufficient permissions for your Notion integration. "),
    (Blocks, Pages, 403, False, "This is likely due to insufficient permissions for your Notion integration. "),
    (Users, None, 200, True, None)
])
def test_403_error_handling(stream, parent, status_code, expected_availability, expected_reason_substring):
    """
    Test that availability strategy handles 403 errors as expected.
    """

    with patch(f'source_notion.streams.{stream.__name__}._send_request') as mock_send_request:
        mock_resp = requests.Response()
        mock_resp.status_code = status_code

        if status_code == 403:
            mock_resp._content = b'{"object": "error", "status": 403, "code": "restricted_resource"}'
            mock_error = requests.HTTPError(response=mock_resp)
            mock_send_request.side_effect = mock_error
        else:
            mock_resp._content = b'{"object": "list", "results": [{"id": "123", "object": "user", "type": "person"}]}'
            mock_send_request.return_value = mock_resp

        if parent:
            stream = stream(parent=parent, config=MagicMock())
            stream.parent.stream_slices = MagicMock(return_value=[{"id": "123"}])
            stream.parent.read_records = MagicMock(return_value=[{"id": "123", "object": "page"}])
        else:
            stream = stream(config=MagicMock())

        is_available, reason = stream.check_availability(logger=logging.Logger, source=MagicMock())

        assert is_available is expected_availability

        if expected_reason_substring:
            assert expected_reason_substring in reason
        else:
            assert reason is None
