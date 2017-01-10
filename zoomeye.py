#!/usr/bin/env python
# coding: utf8

import json
import socket
import requests
from requests.packages import urllib3
from collections import namedtuple

urllib3.disable_warnings()
socket.setdefaulttimeout(6)

class Zoomeye():
	'''
	Zoomeye_api class 
	'''
	class ZoomeyeException(Exception):			pass
	class ConnectionError(ZoomeyeException):	pass
	class ResponseError(ZoomeyeException):		pass
	class RequestFailed(ZoomeyeException):		pass

	_KIND = namedtuple('_KIND', 'host web')
	_RESOURCES = namedtuple('_RESOURCES', 'plan host web')

	_filter = _KIND(
		('app', 'ver', 'device', 'os', 'service', 'ip', 'cidr', 'hostname', 'port', 'city', 'country', 'asn'),
		('app', 'header', 'keywords', 'desc', 'title', 'ip', 'site', 'city', 'country'),
		)
	_facets = _KIND(
		('app', 'device', 'service', 'os', 'port', 'country', 'city'),
		('webapp', 'component', 'framework', 'frontend', 'server', 'waf', 'os', 'country', 'city'),
		)

	def __init__(self, _user, _passwd):
		self._user = _user
		self._passwd = _passwd
		self._token = None
		self._resources = Zoomeye._RESOURCES(None, None, None)
		self._session = requests.Session()
		self._timeout = 6
		self._headers = dict()

	@property
	def online(self):
		return not self._token is None
	@property
	def plan(self):
		return self._resources.plan
	@property
	def hostSearch(self):
		return self._resources.host
	@property
	def webSearch(self):
		return self._resources.web

	def _request(self, _path, _json=None, _param=None, _method='post'):
		try:
			res = self._session.request(
				method=_method, 
				url='https://api.zoomeye.org%s' % _path, 
				json=_json,
				params=_param,
				timeout=self._timeout, 
				verify=False,
				headers=self._headers,
				allow_redirects=False,
				proxies={'http': 'http://127.0.0.1:8080'})
		except (requests.ConnectionError, requests.Timeout):
			raise Zoomeye.ConnectionError('connect failed')
		if res.status_code in (200, 201):
			return res.content
		elif res.status_code == 400:
			raise Zoomeye.RequestFailed('400 请求错误，请参考 API 文档并重试')
		elif res.status_code == 401:
			try:
				self.login()
			except (Zoomeye.RequestFailed, Zoomeye.ResponseError):
				raise Zoomeye.RequestFailed('401 请求未授权，缺少 token，或者 token 已过期失效')
			return self._request(_path, _json=_json, _param=_param, _method=_method)
		elif res.status_code == 402:
			raise Zoomeye.RequestFailed('402 资源请求额度不足')
		elif res.status_code == 403:
			raise Zoomeye.RequestFailed('403 请求未授权，资源访问权限不够或请求超过限制条件')
		elif res.status_code == 404:
			raise Zoomeye.RequestFailed('404 请求失败，访问资源不存在')
		elif res.status_code == 405:
			raise Zoomeye.RequestFailed('405 请求失败，请求方法不允许')
		elif res.status_code == 422:
			raise Zoomeye.RequestFailed('422 请求失败, 包含非法请求参数，请确认后重试')
		elif res.status_code == 500:
			raise Zoomeye.RequestFailed('500 服务端错误')
		elif res.status_code == 503:
			raise Zoomeye.RequestFailed('503 请求的服务端资源未存在')
		else:
			raise Zoomeye.RequestFailed('%s unsupport http code' % res.status_code)

	def login(self):
		try:
			data = self._request(_path='/user/login', _json={'username':self._user, 'password':self._passwd})
		except Zoomeye.RequestFailed as e:
			raise Zoomeye.RequestFailed('login failed, %s' % e)
		try:
			self._token = 'JWT ' + json.loads(data)['access_token']
		except (ValueError, KeyError):
			raise Zoomeye.ResponseError('invalid json string')
		self._headers['Authorization'] = self._token

	def resources(self):
		try:
			data = self._request(_path='/resources-info', _method='get')
		except Zoomeye.RequestFailed as e:
			raise Zoomeye.RequestFailed('get resources failed, %s' % e)
		try:
			data = json.loads(data)
			self._resources = Zoomeye._RESOURCES(
				data['plan'], 
				int(data['resources']['host-search']), 
				int(data['resources']['web-search']))
		except (ValueError, KeyError):
			raise Zoomeye.ResponseError('invalid json string')

	def searchHost(self, _query, _page=1, _facets=''):
		if not isinstance(_facets, basestring):
			raise ValueError('invalid facets type, "%s"' % type(_facets))
		if ',' in _facets:
			for facet in _facets.split(','):
				if facet not in Zoomeye._facets.host:
					raise ValueError('invlaid facet "%s"' % facet)
		if not isinstance(_page, int):
			raise ValueError('invalid page "%s"' % _page)
		if not isinstance(_query, basestring):
			raise ValueError('invalid query type, "%s"' % type(_query))

		try:
			return json.loads(
				self._request(_path='/host/search', _param={'query':_query, 'page':_page, 'facets':_facets}, _method='get')
				)['matches']
		except Zoomeye.RequestFailed as e:
			raise
		except ValueError:
			raise Zoomeye.ResponseError('invalid json string')

	def searchWeb(self, _query, _page=1, _facets=''):
		if ',' in _facets:
			for facet in _facets.split(','):
				if facet not in Zoomeye._facets.host:
					raise ValueError('invlaid facet "%s"' % facet)
		if not isinstance(_page, int):
			raise ValueError('invalid page "%s"' % _page)
		if not isinstance(_query, basestring):
			raise ValueError('invlid query type "%s"' % type(_query))

		try:
			return json.loads(
				self._request(_path='/web/search', _param={'query':_query, 'page':_page, 'facets':_facets}, _method='get')
				)['matches']
		except Zoomeye.RequestFailed as e:
			raise
		except ValueError:
			raise Zoomeye.ResponseError('invalid json string')

	def iterResult(self, _func, _query, _page=1, _facets=''):
		_retry_times = 5
		while True:
			_page += 1
			try:
				matches_list = _func(_query=_query, _page=_page, _facets=_facets)
				_retry_times = 5
			except Zoomeye.RequestFailed as e:
				raise StopIteration
			except Zoomeye.ResponseError as e:
				_page -= 1
				if _retry_times > 0:
					continue
				raise StopIteration

			for matches in matches_list:
				yield matches
