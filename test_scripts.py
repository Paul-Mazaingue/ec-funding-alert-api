from src.utils import load_json, save_json, delete_json
from src.query import generate_query
from src.request import request_api_async
from src.facet import get_value_from_rawValue, get_rawValue_from_value, get_all_values, request_facet_api
from src.mail import send_email_alert
from src.fetch import fetch_all_calls, get_detailed_info
import asyncio

def test_utils():
    data = {"name": "John", "age": 30}
    file_path = "example.json"
    try:
        assert save_json(data, file_path)
        loaded_data = load_json(file_path)
        assert loaded_data == data
        assert delete_json(file_path)
        return True
    except Exception:
        return False

def test_query():
    try:
        query = generate_query(
            text_search="Digital",
            framework_programmes="43108390",
            call_identifier="HORIZON-CL5-2024-D3-01",
            starting_date_range={"gte": 1672441200000, "lte":1710889200000},
            deadline_range={"gte":1704063600000, "lte":1713304800000},
            statuses=["31094502", "31094503"],
            types=["1","2"]
        )
        assert isinstance(query, dict)
        return True
    except Exception:
        return False

def test_request_api():
    try:
        url = "https://api.tech.ec.europa.eu/search-api/prod/rest/facet"
        params = {"apiKey": "SEDIA", "text": "***"}
        file_paths = {
            'query': 'config/facet.json',
            'languages': 'config/languages.json'
        }
        result = asyncio.run(request_api_async(url, params, file_paths))
        if not result:
            return False

        url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
        params = {"apiKey": "SEDIA", "text": "***"}
        file_paths = {
            'query': 'config/query.json',
            'languages': 'config/languages.json',
            'sort': 'config/sort.json',
        }
        result = asyncio.run(request_api_async(url, params, file_paths))
        return bool(result)
    except Exception:
        return False

def test_facet():
    try:
        result = request_facet_api('data/facet.json') 
        if not result:
            return False
        if get_rawValue_from_value('Closed', 'status') != "31094503":
            return False
        if get_value_from_rawValue('31094503', 'status') != "Closed":
            return False
        if get_all_values('status') is None:
            return False

        return result
    except Exception as e:
        print("Erreur test_facet:", e)
        return False

def test_send_email_alert():
    try:
        results = [
            {
                "title": "Test Project",
                "starting_date": "2024-01-01",
                "deadline": "2024-12-31",
                "type": "Research",
                "status": "Open",
                "url": "http://example.com",
                "identifier": "12345",
                "reference": "Ref12345",
                "summary": "This is a test project.",
                "frameworkProgramme": "Horizon Europe"
            },
            {
                "title": "Test Project 2",
                "starting_date": "2024-02-01",
                "deadline": "2024-11-30",
                "type": "Innovation",
                "status": "Closed",
                "url": "http://example.com/2",
                "identifier": "67890",
                "reference": "Ref67890",
                "summary": "This is another test project.",
                "frameworkProgramme": "Horizon Europe"
            }
        ]
        receivers = ["p.mazaingue@ideta.be"]
        alert_template = "<strong>{title}</strong>\r\n{summary}\r\n\r\nStarting date : <em>{starting_date}</em>\r\nDeadline: <em>{deadline}</em>\r\n\r\nType : {type}\r\nStatus: {status}\r\n\r\nFramework programme : {frameworkProgramme}\r\n\r\nMore information : {url}"
        send_email_alert(results, alert_template, receivers)
        return True
    except Exception as e:
        print("Erreur test_send_email_alert:", e)
        return False
    
def test_fetch_all_calls():
    try:
        alert = {
            "name" : "Test Alert",
            "keywords": ["test"],
            "file_paths": {
                'query': 'config/query.json',
                'languages': 'config/languages.json',
                'sort': 'config/sort.json',
            }
        }
        results = asyncio.run(fetch_all_calls(alert))

        reference = "45645052HORIZONResearchandInnovationActions1694476800000"
        identifier = "HORIZON-CL5-2024-D3-01-14"

        details = asyncio.run(get_detailed_info(identifier, reference, alert))

        return bool(results) and bool(details)
    except Exception as e:
        print("Erreur test_fetch_all_calls:", e)
        return False

# Pour lancer les tests manuellement
if __name__ == "__main__":
    print("test_utils:", "OK" if test_utils() else "FAIL")
    print("test_query:", "OK" if test_query() else "FAIL")
    print("test_request_api:", "OK" if test_request_api() else "FAIL")
    print("test_facet:", "OK" if test_facet() else "FAIL")
    print("test_send_email_alert:", "OK" if test_send_email_alert() else "FAIL")
    print("test_fetch_all_calls:", "OK" if test_fetch_all_calls() else "FAIL")
