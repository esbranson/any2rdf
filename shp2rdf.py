#!/usr/bin/python3 -uW all

usage="""Usage: ./shp2rdf.py [-d] config.js"""

import sys
import logging
import functools
import itertools
import json
import getopt

import osgeo.ogr
import rdflib

required_str = [
	"filename_in",
	"filename_out",
	"feat_prefix",
	"geom_prefix",
	"vocab_prefix"
]

required_list_str = [
	"fid_attrs",
	"gid_attrs"
]

optional_default_str = {
	"feat_type": "",
	"feat_prefix_prefix": "",
	"geom_prefix_prefix": "",
	"vocab_prefix_prefix": "",
	"ogc_prefix_prefix": "geo",
	"format": "turtle",
	"fid_sep": "_",
	"fid_prefix": "",
	"fid_postfix": "",
	"gid_sep": "_",
	"gid_prefix": "",
	"gid_postfix": "",
	"label_sep": "_",
	"label_prefix": "",
	"label_postfix": ""
}

# NOTE order matter here
optional_list_str = [
	"label_attrs",
	"fid_functs",
	"gid_functs",
	"label_functs"
]

#optional_list_dict = [
#	"attrs"
#]

required_list_dict_str = [
	"name"
]

required_list_dict_list_str = [
	"attrs"
]

optional_list_dict_list_str = [
	"functs"
]

optional_list_dict_default_str = {
	"prefix": "",
	"postfix": "",
	"sep": "_",
	"type": ""
}

def open_conf(conffn):
	f = open(conffn)
	conf = json.load(f)
	f.close()

	if not isinstance(conf, dict):
		logging.fatal('Configuration must be a JSON dictionary.')
		sys.exit(1)

	for key in required_str:
		if key not in conf:
			logging.fatal('Key {} not in configuration.'.format(key))
			sys.exit(1)
		if not isinstance(conf[key], str):
			logging.fatal('Key {} must be a string.'.format(key))
			sys.exit(1)

	for key in required_list_str:
		if key not in conf:
			logging.fatal('Key {} not in configuration.'.format(key))
			sys.exit(1)
		if not isinstance(conf[key], list) or not functools.reduce(lambda _t,_v: _t and isinstance(_v, str), conf[key], True):
			logging.fatal('Key {} must be a string.'.format(key))
			sys.exit(1)

	for key in optional_default_str:
		if key not in conf:
			conf[key] = optional_default_str[key]

	for key in optional_list_str:
		if key.endswith('_functs'):
			l = len(conf[key.split('_',1)[0]+'_attrs'])
		else:
			l = 0
		if key not in conf:
			conf[key] = [''] * l
		elif not isinstance(conf[key], list) or not functools.reduce(lambda _t,_v: _t and isinstance(_v, str), conf[key], True):
			logging.warning('Needs to be list of strings: {}'.format(key))
			conf[key] = [''] * l
		elif l != 0 and len(conf[key]) < l: # key.endswith('_functs')
			logging.warning('Padding {} with empty elements.'.format(key))
			for i in range(l-len(conf[key])):
				conf[key].append('')

#	for key in optional_list_dict:
#		if key not in conf:
#			conf[key] = []

	if 'attrs' not in conf:
		conf['attrs'] = []

	for item in conf['attrs']:
		if not isinstance(item, dict):
			logging.fatal('Attribute must be a dictionary.')
			sys.exit(1)

		for key in required_list_dict_str:
			if key not in item:
				logging.fatal('Key {} not in configuration.'.format(key))
				sys.exit(1)
			if not isinstance(item[key], str):
				logging.fatal('Key {} must be a string.'.format(key))
				sys.exit(1)

		for key in required_list_dict_list_str:
			if key not in item:
				logging.fatal('Key {} not in configuration.'.format(key))
				sys.exit(1)
			if not isinstance(item[key], list) or not functools.reduce(lambda _t,_v: _t and isinstance(_v, str), item[key], True):
				logging.fatal('Key {} must be a string.'.format(key))
				sys.exit(1)

		for key in optional_list_dict_default_str:
			if key not in item:
				item[key] = optional_list_dict_default_str[key]

		for key in optional_list_dict_list_str:
			if key == 'functs':
				l = len(item['attrs'])
			else:
				l = 0
			if key not in item:
				item[key] = [''] * l
			elif not isinstance(item[key], list) or not functools.reduce(lambda _t,_v: _t and isinstance(_v, str), item[key], True):
				logging.warning('Needs to be list of strings: {}'.format(key))
				item[key] = [''] * l

	logging.debug('{}'.format(str(conf)))

	return conf

def FeatureGen(layer):
	assert layer
	feature = layer.GetNextFeature()
	while feature:
		yield feature
		feature = layer.GetNextFeature()

def convert(conf):
	g = rdflib.Graph()
	featns = rdflib.Namespace(conf['feat_prefix'])
	if len(conf['feat_prefix_prefix']):
		g.bind(conf['feat_prefix_prefix'], featns)
	geomns = rdflib.Namespace(conf['geom_prefix'])
	if len(conf['geom_prefix_prefix']):
		g.bind(conf['geom_prefix_prefix'], geomns)
	vocabns = rdflib.Namespace(conf['vocab_prefix'])
	if len(conf['vocab_prefix_prefix']):
		g.bind(conf['vocab_prefix_prefix'], vocabns)
	if len(conf['ogc_prefix_prefix']):
		g.bind(conf['ogc_prefix_prefix'], 'http://www.opengis.net/ont/geosparql#')
#	geons = rdflib.Namespace('http://www.opengis.net/ont/geosparql#')
	geofeat = rdflib.URIRef('http://www.opengis.net/ont/geosparql#Feature')
	geohasgeom = rdflib.URIRef('http://www.opengis.net/ont/geosparql#hasGeometry')
	geogeom = rdflib.URIRef('http://www.opengis.net/ont/geosparql#Geometry')
	geoaswkt = rdflib.URIRef('http://www.opengis.net/ont/geosparql#asWKT')
	geowkt = rdflib.URIRef('http://www.opengis.net/ont/geosparql#wktLiteral')

	driver = osgeo.ogr.GetDriverByName('ESRI Shapefile')
	shp = driver.Open(conf['filename_in'])
	lyr = shp.GetLayer()
	maxim = lyr.GetFeatureCount()
	for n,feat in enumerate(FeatureGen(lyr), 1):
		if feat is None:
			logging.warning('Feature {} is empty.'.format(n))
		# get feature ID
		try:
			fidents = [_f and eval(_f)(feat.GetFieldAsString(_a)) or feat.GetFieldAsString(_a) for _a,_f in zip(conf['fid_attrs'],conf['fid_functs'])]
			if functools.reduce(lambda _t,_v: _t or not isinstance(_v, str) or len(_v) == 0, fidents, False):
				logging.info('Feature {} parse returned empty FID: {}'.format(n,fidents))
				continue
			fident = conf['fid_sep'].join(fidents)
		except UnicodeDecodeError as e:
			logging.warning('Feature {} not decoded: {}'.format(n,e))
			fident = 'unkownfeature_'+n
		if len(conf['fid_prefix']):
			fident = ''.join([conf['fid_prefix'], fident])
		if len(conf['fid_postfix']):
			fident = ''.join([fident, conf['fid_postfix']])
#		g.add((featns[fident], rdflib.RDF.type, geofeat))
		if len(conf['feat_type']):
			g.add((featns[fident], rdflib.RDF.type, vocabns[conf['feat_type']]))
		else:
			g.add((featns[fident], rdflib.RDF.type, geofeat))

		# get geometry ID
		try:
			gident = conf['gid_sep'].join([_f and eval(_f)(feat.GetFieldAsString(_a)) or feat.GetFieldAsString(_a) for _a,_f in zip(conf['gid_attrs'],conf['gid_functs'])])
		except UnicodeDecodeError as e:
			logging.warning('Geometry {} not decoded: {}'.format(n,e))
			gident = 'unknowngeometry_'+n
		if len(conf['gid_prefix']):
			gident = ''.join([conf['gid_prefix'], gident])
		if len(conf['gid_postfix']):
			gident = ''.join([gident, conf['gid_postfix']])
		g.add((geomns[gident], rdflib.RDF.type, geogeom))
		g.add((featns[fident], geohasgeom, geomns[gident]))

		# get label
		try:
			label = conf['label_sep'].join([_f and eval(_f)(feat.GetFieldAsString(_a)) or feat.GetFieldAsString(_a) for _a,_f in zip(conf['label_attrs'],conf['label_functs'])])
		except UnicodeDecodeError as e:
			logging.warning('Label {} not decoded: {}'.format(n,e))
			label = ''
		if len(conf['label_prefix']):
			label = ''.join([conf['label_prefix'], label])
		if len(conf['label_postfix']):
			label = ''.join([label, conf['label_postfix']])
		if label and len(label):
			g.add((featns[fident], rdflib.RDFS.label, rdflib.Literal(label, lang='en')))

		# get geometry
		geom = feat.GetGeometryRef()
		if geom is None:
			logging.warning('Geometry {} {} is empty.'.format(n,fident))
		else:
			wkt = geom.ExportToWkt()
			g.add((geomns[gident], geoaswkt, rdflib.Literal(wkt, datatype=geowkt)))

#		print(fident,gident,label,wkt[:20])

		for attrs in conf['attrs']:
			try:
				val = attrs['sep'].join([_f and eval(_f)(feat.GetFieldAsString(_a)) or feat.GetFieldAsString(_a) for _a,_f in zip(attrs['attrs'],attrs['functs'])])
			except UnicodeDecodeError as e:
				logging.warning('Attribute {} not decoded: {}'.format(n,e))
				val = 'unknownattribute_'+n
			if val and len(attrs['prefix']):
				val = ''.join([attrs['prefix'], val])
			if val and len(attrs['postfix']):
				val = ''.join([val, attrs['postfix']])
			if val: # can use functs to filter e.g. NULLs
				prop = attrs['name'] # XXX defaults in open_conf
#				if len(attrs['ident_attrs']): # XXX
				if False:
					aident = attrs['sep'].join([_f and eval(_f)(feat.GetFieldAsString(_a)) or feat.GetFieldAsString(_a) for _a,_f in zip(attrs['ident_attrs'],attrs['ident_functs'])])
					if len(attrs['type']):
						g.add((featns[aident], vocabns[prop], rdflib.Literal(val, datatype=rdflib.URIRef(attrs['type']))))
					else:
						g.add((featns[aident], vocabns[prop], rdflib.URIRef(val)))
				else:
					if len(attrs['type']):
						g.add((featns[fident], vocabns[prop], rdflib.Literal(val, datatype=rdflib.URIRef(attrs['type']))))
					else:
						g.add((featns[fident], vocabns[prop], rdflib.URIRef(val)))

		if n % 10000 == 0:
			logging.debug('Converted {}/{} features'.format(n,maxim))

	logging.info('Serializing')

	g.serialize(conf['filename_out'], format=conf['format'])

def main():
	opts, args = getopt.getopt(sys.argv[1:], 'd')
	opts = dict(opts)

	if len(args) != 1:
		logging.fatal('Invalid usage.\n{}'.format(usage))
		sys.exit(1)
	conffn = args[0]

	if '-d' in opts:
		lvl = logging.DEBUG
	else:
		lvl = logging.INFO
	logging.basicConfig(format='{levelname:8s}: {message}', style='{', level=lvl)

	conf = open_conf(conffn)
	convert(conf)

if __name__ == '__main__':
	main()

