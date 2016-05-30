# -*- coding: utf-8 -*-
import re
import scrapy

from ssptransparencia.items import *


def get_postback(a_selector):
    href = a_selector.xpath('@href').extract_first()
    m = re.match(r"javascript:__doPostBack\('(.*)','(.*)'\)", href)
    assert m
    return {'__EVENTTARGET': m.group(1), '__EVENTARGUMENT': m.group(2)}


class SsptransparenciaBaseSpider(scrapy.Spider):
    allowed_domains = ["ssp.sp.gov.br"]
    start_urls = (
        'http://www.ssp.sp.gov.br/transparenciassp/Consulta.aspx',
    )

    def parse(self, response):
        a = response.css(self.first_lvl_link_css)
        yield scrapy.FormRequest.from_response(response, formid='frmMain',
            formdata=get_postback(a),
            dont_click=True, callback=self.parse_years)

    def parse_years(self, response):
        a_list = response.css('#cphBody_divDados ul.anoNav li a')
        if not a_list:
            self.logger.warning('No years found')
        for a in a_list:
            year = a.xpath('./text()').extract_first()
            yield scrapy.FormRequest.from_response(response, formid='frmMain',
                formdata=get_postback(a),
                dont_click=True, callback=self.parse_months,
                meta={'year': year})

    def parse_months(self, response):
        year = response.meta['year']
        a_list = response.css('#cphBody_divDados ul.mesNav li a')
        if not a_list:
            self.logger.warning('No months found for %s', year)
        for a in a_list:
            month = a.xpath('./text()').extract_first()
            yield scrapy.FormRequest.from_response(response, formid='frmMain',
                formdata=get_postback(a),
                dont_click=True, callback=self.parse_pages,
                meta={'year': year, 'month': month})

    def parse_pages(self, response):
        for item in self.parse_rows(response):
            # process rows from first page
            yield item
        year = response.meta['year']
        month = response.meta['month']
        for a in response.css('tr.pager_row table td a'):
            if a.xpath('./text()').extract_first() == '...':
                callback = self.parse_pages
            else:
                callback = self.parse_rows
            yield scrapy.FormRequest.from_response(response, formid='frmMain',
                formdata=get_postback(a),
                dont_click=True, callback=callback,
                meta={'year': year, 'month': month})

    def parse_rows(self, response):
        count = 0
        year = response.meta['year']
        month = response.meta['month']
        url = 'http://www.ssp.sp.gov.br/transparenciassp/Consulta.aspx/AbrirBoletim'
        headers = {'Content-Type': 'application/json; charset=UTF-8;'}
        _first = lambda sel, xpath: sel.xpath(xpath).extract_first()
        for row in response.css('table#cphBody_grdListBO tr'):
            if row.xpath('@class').extract_first() in ['row1', 'row2']:
                count += 1
                row_onclick = row.xpath('./td[1]/a/@onclick').extract_first()
                m = re.match(r'relatorioBO\((.*),(.*),(.*)\);', row_onclick)
                assert m
                year = m.group(1).strip()
                occurrence = m.group(2).strip()
                station = m.group(3).strip()
                body = '{ anoBO: %s, numBO: %s, delegacia: %s }' % (year, occurrence, station)
                meta = {
                    'id': '%s-%s-%s' % (year, occurrence, station),
                    'nav_ano': year,
                    'nav_mes': month,
                    'tabela_numero_bo': _first(row, 'td[1]/a/text()'),
                    'tabela_tipo_bo': _first(row, 'td[2]/text()'),
                    'tabela_cidade': _first(row, 'td[3]/text()'),
                    'tabela_delegacia_elaboracao': _first(row, 'td[4]/text()'),
                    'tabela_data_fato': _first(row, 'td[5]/text()'),
                    'tabela_data_registro': _first(row, 'td[6]/text()'),
                    'tabela_endereco_fato': _first(row, 'td[7]/text()'),
                }
                yield scrapy.Request(url, method='POST', headers=headers, body=body, callback=self.open_occurrence, meta=meta)
        if not count:
            self.logger.warning('No items found for %s-%s', year, month)

    def open_occurrence(self, response):
        url = 'http://www.ssp.sp.gov.br/transparenciassp/BO.aspx'
        yield scrapy.Request(url, dont_filter=True, callback=self.parse_occurrence, meta=response.meta)

    def parse_occurrence(self, response):
        l = SsptransparenciaBOLoader(SsptransparenciaBO(), response)
        l.add_value('id', response.meta['id'])
        l.add_value('nav_ano', response.meta['nav_ano'])
        l.add_value('nav_mes', response.meta['nav_mes'])
        l.add_value('tabela_numero_bo', response.meta['tabela_numero_bo'])
        l.add_value('tabela_tipo_bo', response.meta['tabela_tipo_bo'])
        l.add_value('tabela_cidade', response.meta['tabela_cidade'])
        l.add_value('tabela_delegacia_elaboracao', response.meta['tabela_delegacia_elaboracao'])
        l.add_value('tabela_data_fato', response.meta['tabela_data_fato'])
        l.add_value('tabela_data_registro', response.meta['tabela_data_registro'])
        l.add_value('tabela_endereco_fato', response.meta['tabela_endereco_fato'])
        l.add_xpath('bo_dependencia', u"//div/div/span[contains(., 'Dependência:')]/parent::div/span[2]/text()")
        l.add_xpath('bo_numero', u"//div/div/span[contains(., 'Boletim No.:')]/parent::div/span[2]/text()")
        l.add_xpath('bo_iniciado', u"//div/div/span[contains(., 'Iniciado:')]/parent::div/span[2]/text()")
        l.add_xpath('bo_emitido', u"//div/div/span[contains(., 'Emitido:')]/parent::div/span[5]/text()")
        l.add_xpath('bo_autoria', u"//div/div/span[contains(., 'Boletim de Ocorrencia de Autoria')]/parent::div/span[2]//text()")
        l.add_xpath('bo_complementar_ao_rdo', u"//tr[@valign='top'][contains(., 'Complementar ao R.D.O. nº:')]/following-sibling::tr[@valign='top'][1]//text()")
        l.add_xpath('bo_desdobramentos', u"//tr[@valign='top']/td/div[contains(., 'Desdobramentos:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_local_linha1', u"//tr[@valign='top']/td/div[contains(., 'Local:')][not(contains(., 'Tipo'))]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_local_linha2', u"//tr[@valign='top']/td/div[contains(., 'Local:')][not(contains(., 'Tipo'))]/parent::td/parent::tr/following-sibling::tr[@valign='top'][1]/td[2]//text()")
        l.add_xpath('bo_tipo_local', u"//tr[@valign='top']/td/div[contains(., 'Tipo de Local:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_circunscricao', u"//tr[@valign='top']/td/div[contains(., 'Circunscrição:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_ocorrencia', u"//tr[@valign='top']/td/div[contains(., 'Ocorrência:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_comunicacao', u"//tr[@valign='top']/td/div[contains(., 'Comunicação:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_elaboracao', u"//tr[@valign='top']/td/div[contains(., 'Elaboração:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_flagrante', u"//tr[@valign='top']/td/div[contains(., 'Flagrante:')]/parent::td/following-sibling::td[1]//text()")
        l.add_xpath('bo_exames_requisitados', u"//tr/td[contains(text(), 'Exames requisitados:')]//text()", re=u'Exames requisitados:(.*)')
        l.add_xpath('bo_solucao', u"//tr/td[contains(text(), 'Solução:')]//text()", re=u'Solução:(.*)')
        bo_item = l.load_item()
        yield bo_item

        for tr in response.xpath(u"//tr[@valign='top']/td/div[contains(., 'Espécie:')]/parent::td/parent::tr"):
            l = SsptransparenciaNaturezaLoader(SsptransparenciaNatureza(), tr)
            l.add_value('bo_id', bo_item['id'])
            l.add_xpath('especie', u"./td[2]//text()")
            l.add_xpath('natureza_linha1', u"./following-sibling::tr[@valign='top'][1]/td[2]//text()")
            l.add_xpath('natureza_linha2', u"./following-sibling::tr[@valign='top'][2]/td[2]//text()")
            natureza_item = l.load_item()
            yield natureza_item

        for sel in response.xpath(u"//*[contains(text(), '(Vítima)')]|//*[contains(text(), '(Autor/Vitima)')]"):
            line = ' '.join(sel.xpath('.//text()').extract())
            l = SsptransparenciaVitimaLoader(SsptransparenciaVitima(), sel)
            l.add_value('bo_id', bo_item['id'])
            l.add_value('nome', line, re=u'^(.*?)\(.*?Vítima.*?\)')
            l.add_value('autor_vitima', line, re=u'\((.*?Vítima.*?)\)')
            l.add_value('tipo', line, re=u'\(.*?Vítima.*?\).*?\-(.*?)\-')
            l.add_value('rg', line, re='RG: *(\d+\-[A-Z]{2})')
            l.add_value('natural_de', line, re='Natural de: *(.*?\-[A-Z]{2})')
            l.add_value('nacionalidade', line, re='Nacionalidade: *(.+?) ')
            l.add_value('sexo', line, re='Sexo: *(.+?) ')
            l.add_value('nascimento', line, re='Nascimento: *(.+?) ')
            l.add_value('idade', line, re='(\d+) anos')
            l.add_value('estado_civil', line, re='Estado Civil: *(.+?)\-')
            l.add_value('profissao', line, re=u'Profissão: *(.+?)\-')
            l.add_value('instrucao', line, re=u'Instrução: *(.+?)\-')
            l.add_value('cutis', line, re=u'Cutis: *(.+?)\-')
            l.add_value('naturezas_envolvidas', line, re=u'Naturezas Envolvidas:(.+)')
            vitima_item = l.load_item()
            yield vitima_item
