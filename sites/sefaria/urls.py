# -*- coding: utf-8 -*-

from django.conf.urls import url
from django.http import HttpResponseRedirect
import reader.views as reader_views
from sefaria.settings import STATIC_URL


static_pages = [
    "about",
    "donate",
    "strategy",
    "supporters",
    "team",
    "help",
    "connect",
    "visualizations",
    "jobs",
    "terms",
    "privacy-policy",
    "coming-soon",
    "shraga-silverstein",
    "henry-and-julia-koschitzky-apps",
    "adin-even-israel-steinsaltz",
    "william-davidson-talmud",
    "linker",
    "ios",
    "mobile",
    "app",
    "sefaria-edition",
    "sefaria-community-translation",
    "contributed-to-sefaria",
    "random-walk-through-torah",
    "educators",
    "the-sefaria-story",
    "aramaic-translation-contest",
    "newsletter",
    "shavuot-map-2018",
    "testimonials",
    "torah-tab",
    "dicta-thanks",
    "daf-yomi",
    "remote-learning",
    "sheets",
    "powered-by-sefaria-contest-2020",
]


# Static and Semi Static Content
site_urlpatterns = [
    url(r'^$', reader_views.home, name="home"),
    url(r'^enable_new_editor/?$', reader_views.enable_new_editor),
    url(r'^disable_new_editor/?$', reader_views.disable_new_editor),
    url(r'^metrics/?$', reader_views.metrics),
    url(r'^digitized-by-sefaria/?$', reader_views.digitized_by_sefaria),
    url(r'^apple-app-site-association/?$', reader_views.apple_app_site_association),
    url(r'^\.well-known/apple-app-site-association/?$', reader_views.apple_app_site_association),
    url(r'^(%s)/?$' % "|".join(static_pages), reader_views.serve_static),
    url(r'^healthz/?$', reader_views.application_health_api),
]


# Redirects to Wikis etc
site_urlpatterns += [
    url(r'^wiki/?$', lambda x: HttpResponseRedirect('https://github.com/Sefaria/Sefaria-Project/wiki')),
    url(r'^developers/?$', lambda x: HttpResponseRedirect('https://github.com/Sefaria/Sefaria-Project/wiki#developers')),
    url(r'^request-a-text/?$', lambda x: HttpResponseRedirect('https://goo.gl/forms/ru33ivawo7EllQxa2')),
    url(r'^request-a-training/?$', lambda x: HttpResponseRedirect(' https://docs.google.com/forms/d/1CJZHRivM2qFeF2AE2afpvE1m86AgJPCxUEFu5EG92F8/edit?usp=sharing_eil&ts=5a4dc5e0')),
    url(r'^contribute/?$', lambda x: HttpResponseRedirect('https://github.com/Sefaria/Sefaria-Project/wiki/Guide-to-Contributing')),
    url(r'^faq/?$', lambda x: HttpResponseRedirect('https://www.sefaria.org/collections/sefaria-faqs' if x.interfaceLang == 'english' else 'https://www.sefaria.org/collections/%D7%A9%D7%90%D7%9C%D7%95%D7%AA-%D7%A0%D7%A4%D7%95%D7%A6%D7%95%D7%AA-%D7%91%D7%A1%D7%A4%D7%A8%D7%99%D7%90')),
    url(r'^gala/?$', lambda x: HttpResponseRedirect('https://www.501auctions.com/sefaria')),
    url(r'^jfn?$', lambda x: HttpResponseRedirect('https://www.sefaria.org/sheets/60494')),
    url(r'^[nN]echama/?', lambda x: HttpResponseRedirect("/collections/גיליונות-נחמה")),
    url(r'^contest?', lambda x: HttpResponseRedirect("/powered-by-sefaria-contest-2020")),    
]


site_urlpatterns +=[
    url(r'^textmap/?$', lambda x: HttpResponseRedirect(STATIC_URL + 'files/Sefaria-Text-Map-June-2016.pdf')),
    url(r'^workshop/?$', lambda x: HttpResponseRedirect(STATIC_URL + 'files/Sefaria_SummerMeeting_2016.pdf')),
    url(r'^ideasforteaching/?$',lambda x: HttpResponseRedirect(STATIC_URL + 'files/Sefaria_Teacher_Generated_Ideas_for_Your_Classroom.pdf')),
    url(r'^strategicplan/?$',lambda x: HttpResponseRedirect(STATIC_URL + 'files/Sefaria_Strategic_Plan.pdf')),
    url(r'^annualreport/?$', lambda x: HttpResponseRedirect(STATIC_URL + 'files/Annual_Report_71420.pdf')),
]
