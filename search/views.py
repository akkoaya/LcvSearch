from django.shortcuts import render
from django.views.generic.base import View
from search.models import CnblogPost
from django.http import HttpResponse
import json
from elasticsearch_dsl.connections import connections
from datetime import datetime
import redis
es = connections.get_connection()
redis_cli = redis.StrictRedis(host="localhost")

class IndexView(View):
    def get(self, request):
        key_words = request.GET.get('s', '')
        redis_cli.zincrby('search_words', 1, key_words)
        search_word = redis_cli.zrevrangebyscore('search_words', "+inf", "-inf", start=1, num=5)
        search_words = []
        for se in search_word:
            search = se.decode()
            search_words.append(search)
        return render(request, "index.html", {"search_words": search_words})



class SearchSuggest(View):
    def get(self, request):
        key_words = request.GET.get('s','')  #后面的是默认值
        #因为在index.html中是：url:suggest_url+"?s="+searchText+"&s_type="+$(".searchItem.current").attr('data-type'),
        #取's'里的内容，这个是搜索输入的内容
        re_data = []
        if key_words:
            s = CnblogPost.search()
            re = s.suggest("suggest_1",key_words,completion={
                "field":"suggest",
                "fuzzy":{
                    "fuzziness": "auto"
                },
                "size":5
            })#size表示返回的数量

            suggests = re.execute()

            for match in suggests.suggest.suggest_1[0].options:
                source = match._source
                re_data.append(source["title"])

        return  HttpResponse(json.dumps(re_data), content_type="application/json")

class SearchView(View):
    def get(self, request):
        cnblog_nums = redis_cli.get('cnblog_nums').decode()
        start_time = datetime.now()
        key_words = request.GET.get('q', '')
        #window.location.href=search_url+'?q='+val+"&s_type="+$(".searchItem.current").attr('data-type')
        #取'q'里的内容，这个是搜索输入的内容
        s_type = request.GET.get("s_type", "article")
        key_word = key_words.lower()

        redis_cli.zincrby('search_words',1,key_words)
        search_word = redis_cli.zrevrangebyscore('search_words', "+inf", "-inf", start=1, num=5)
        search_words = []
        for se in search_word:
            search = se.decode()
            search_words.append(search)

        page = request.GET.get('p', '1')
        try:
            page = int(page)
        except:
            page = 1

        re = es.search(
        index='cnblog',
        body={
            "query": {
                "bool": {
                    "should":[
                        {"fuzzy":{"title":{"value":key_word,"fuzziness":1}}},
                        {"fuzzy":{"main_content":{"value":key_word,"fuzziness":1}}},
                ]}},
            "from": (page-1)*10,
            "size": 10,
            # 匹配到的搜索字标红处理
            "highlight": {
                "pre_tags": ['<span class="keyWord">'],
                "post_tags": ["</span>"],
                "fields": {
                    "title": {},
                    "main_content": {}
                }}})


        total_nums = re.body["hits"]["total"]["value"]

        if (total_nums%10) > 0:
            page_nums = int(total_nums/10) + 1
        else:
            page_nums = int(total_nums/10)

        hit_list = []
        for hit in re.body["hits"]["hits"]:
            hit_dict = {}

            if "title" in  hit["highlight"]:
                hit_dict["title"] = hit["highlight"]["title"][0]
            else:
                hit_dict["title"] = hit["_source"]["title"]
            if  "main_content" in hit["highlight"]:
                hit_dict["main_content"] = ''.join(hit["highlight"]["main_content"][0][:200])+"</span>"
            else:
                hit_dict["main_content"] = ''.join(hit["_source"]["main_content"][:200])+"</span>"

            hit_dict["date"] = hit["_source"]["date"].replace("T"," ")
            hit_dict["url"] = hit["_source"]["url"]
            hit_dict["score"] =  hit["_score"]

            hit_list.append(hit_dict)
        end_time = datetime.now()
        used_time = (end_time - start_time).total_seconds()
        return render(request, "result.html", {"all_hits":hit_list,
                                               "key_words":key_words,
                                               "page":page,
                                               "total_nums":total_nums,
                                               "page_nums":page_nums,
                                               "uesd_time":used_time,
                                               "cnblog_nums": cnblog_nums,
                                               # "search_words":search_words
                                               })

