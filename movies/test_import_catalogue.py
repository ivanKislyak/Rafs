"""Broad-import checks: fixture HTTP and isolated Django databases only."""
import copy
import io
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from movies.management.commands import import_animation as animation
from movies.management.commands.import_series import Command as SeriesCommand
from movies.models import Movie, GlobalSearchIndex
from movies.movie_models import Country, TypeOfWork
from movies.services.catalogue_import import CatalogueState, catalogue_config, selected_countries
from movies.services.animation_state import AnimationState
from movies.test_import_animation import FixtureAPI as AnimationAPI, detail
from movies.test_import_anime import entity, statement


def state_config(importer='series-v1', **kwargs):
    return {'importer': importer, 'schema_version': 2, 'sources': ['tv'],
            'date_from': '2020-02-28', 'date_to': '2020-03-01', 'countries': [],
            'sort': 'popularity.desc', 'min_votes': 0, 'exclude_anime': False, **kwargs}


class FixtureAPI(AnimationAPI):
    def get(self, url, params=None):
        params = params or {}
        if '/discover/' not in url:
            return super().get(url, params)
        if self.require_outside_atomic:
            assert not connection.in_atomic_block
        type(self).requests.append((url, dict(params)))
        assert params['page'] <= 500
        assert not {'with_genres', 'with_keywords', 'with_original_language', 'with_watch_providers', 'with_type', 'with_networks'} & params.keys()
        if any('date' in key and key.endswith('.gte') for key in params):
            return {'results': [], 'total_pages': 0, 'total_results': 0}
        media = url.rsplit('/', 1)[-1]
        ids = sorted(number for (kind, number), item in self.items.items() if kind == media
                     and (not params.get('with_origin_country') or params['with_origin_country'] in item.get('origin_country', [])))
        offset = (params['page'] - 1) * 20
        return {'results': [{'id': value} for value in ids[offset:offset + 20]],
                'total_pages': (len(ids) + 19) // 20, 'total_results': len(ids)}


class CatalogueStateTests(SimpleTestCase):
    def test_country_codes_are_canonical_and_only_supported_production_selections(self):
        self.assertEqual(selected_countries('kz,ru,ru,ua'), ['RU', 'UA', 'KZ'])
        for value in ('', 'SU', 'US', 'RU,XX'):
            with self.subTest(value=value), self.assertRaises(CommandError):
                selected_countries(value)

    def test_target_defaults_to_unlimited_and_can_exceed_15000(self):
        command = SeriesCommand()
        parser = command.create_parser('manage.py', 'import_series')
        options = vars(parser.parse_args([]))
        self.assertEqual(options['target_new'], 0)
        self.assertEqual(command.configuration(options, None)['sources'], ['tv'])
        options['target_new'] = 20000
        command.configuration(options, None)
        options['target_new'] = -1
        with self.assertRaises(CommandError):
            command.configuration(options, None)

    def test_foreign_animation_and_new_campaign_states_are_rejected_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = AnimationState(directory, state_config(importer='animation-v2'))
            state.db.close()
            path = Path(directory) / 'state.sqlite3'
            before = path.read_bytes()
            with self.assertRaises(CommandError):
                catalogue_config(directory)
            self.assertEqual(path.read_bytes(), before)
        with tempfile.TemporaryDirectory() as directory:
            cfg = state_config()
            state = CatalogueState(directory, cfg)
            state.db.close()
            path = Path(directory) / 'state.sqlite3'
            before = path.read_bytes()
            for changed in ({**cfg, 'importer': 'country-movies-v1'}, {**cfg, 'countries': ['RU']}, {**cfg, 'database_fingerprint': 'other'}):
                with self.assertRaises(CommandError):
                    CatalogueState(directory, changed)
                self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(CommandError):
                AnimationState(directory, state_config(importer='animation-v2'))
            self.assertEqual(path.read_bytes(), before)

    def test_country_priority_passes_are_separate_and_ids_are_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            state = CatalogueState(directory, state_config('country-movies-v1', sources=['movie'], countries=['RU', 'UA', 'KZ']))
            try:
                modes = [r[0] for r in state.db.execute('SELECT mode FROM partitions ORDER BY id')]
                self.assertEqual(modes, ['origin-RU', 'origin-UA', 'origin-KZ', 'unfiltered', 'dated'])
                for _ in range(4):
                    state.save_pages([(state.next_partition('movie'), {'results':[{'id':42}], 'total_pages':1})])
                self.assertEqual(len(state.candidates(20)), 1)
            finally:
                state.db.close()

    def test_overflow_partitions_cover_boundaries_and_never_request_page_501(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = state_config()
            state = CatalogueState(directory, cfg)
            try:
                state.db.execute("UPDATE partitions SET status='done' WHERE mode='unfiltered'")
                state.db.commit()
                state.save_pages([(state.next_partition('tv'), {'results':[{'id':1}], 'total_pages':501, 'total_results':10001})])
                intervals = [tuple(r) for r in state.db.execute("SELECT lower_date,upper_date FROM partitions WHERE status='pending' ORDER BY id")]
                self.assertEqual(intervals, [('2020-02-28','2020-02-29'), ('2020-03-01','2020-03-01')])
                state.db.execute("UPDATE partitions SET status='done' WHERE status='pending'")
                state.db.execute("UPDATE partitions SET status='pending',page=499,pages=500 WHERE mode='dated' AND lower_date='2020-03-01'")
                state.db.commit()
                command = SeriesCommand(stdout=io.StringIO())
                command.state, command.config, command.secrets = state, cfg, []
                command.api = Mock()
                command.api.get.return_value = {'results':[{'id':2}], 'total_pages':501, 'total_results':10001}
                self.assertTrue(command.discover_round())
                parameters = command.api.get.call_args.args[1]
                self.assertEqual(parameters['page'], 500)
                self.assertEqual(parameters['first_air_date.gte'], '2020-03-01')
                self.assertNotIn('with_genres', parameters)
                self.assertFalse(command.discover_round())
                self.assertEqual(command.api.get.call_count, 1)
                self.assertEqual(state.statistics()['coverage_limited_partitions'], 1)
            finally:
                state.db.close()


class ImportFixtures:
    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = io.StringIO()
        FixtureAPI.items = {('tv',1): detail('tv',1), ('movie',1): detail('movie',1)}
        FixtureAPI.items[('tv',1)].update(genres=[{'id':18}], keywords={'results':[]}, type='Reality')
        FixtureAPI.items[('movie',1)].update(production_countries=[{'iso_3166_1':'RU'}], origin_country=['RU'])
        FixtureAPI.documents = {
            'Q1001': entity('Q1001',P31=['Q24862'],P4947=['1'],P345=['tt1001'],P495=['Q159']),
            'Q2001': entity('Q2001',P31=['Q5398426'],P4983=['1'],P345=['tt2001']),
            'Q24862': entity('Q24862',P279=['Q11424']),
            'Q5398426': entity('Q5398426'),
            'Q63952888': entity('Q63952888',P279=['Q5398426']),
            'Q159': entity('Q159',P297=['RU']), 'Q212': entity('Q212',P297=['UA']),
            'Q232': entity('Q232',P297=['KZ']), 'Q30': entity('Q30',P297=['US']),
        }
        FixtureAPI.requests, FixtureAPI.bindings = [], []
        FixtureAPI.require_outside_atomic = False

    def run_import(self, command='import_series', **kwargs):
        directory = kwargs.pop('directory', self.root / command)
        with patch.object(animation, 'AnimeAPI', FixtureAPI), patch.dict('os.environ', {'TMDB_READ_TOKEN':'fixture-token','TMDB_API_KEY':''}):
            return call_command(command, state_dir=str(directory), stdout=self.output, **kwargs)

    def report(self, command='import_series', directory=None):
        return json.loads(((directory or self.root/command)/'summary.json').read_text())

    def skip_reason(self, command='import_series'):
        return self.report(command)['campaign_state']['skips_by_reason']


@skipUnless(connection.vendor == 'postgresql', 'Shared lock and search require isolated PostgreSQL')
class CatalogueImportTests(ImportFixtures, TestCase):
    def test_plain_series_without_genre_keyword_or_scripted_filter_and_six_translations(self):
        self.run_import()
        movie = Movie.objects.get()
        self.assertEqual(movie.wikidata_id, 'Q2001')
        self.assertEqual(movie.type_of_work.wikidata_id, 'Q5398426')
        self.assertEqual(movie.year, 2001)
        self.assertEqual(movie.cover_url, 'https://image.tmdb.org/t/p/w500/poster.jpg')
        self.assertEqual(set(movie.translations.values_list('language_code',flat=True)), {'en','ru','uk','kk','es','de'})
        self.assertEqual(self.report()['created_in_campaign'], 1)
        self.assertIsNone(self.report()['target_new'])
        self.assertEqual(GlobalSearchIndex.objects.count(),1)
        self.assertTrue(all('/tv/' in url or '/discover/tv' in url or url.endswith('/configuration') for url,_ in FixtureAPI.requests))

    def test_existing_anime_and_specific_type_are_not_reclassified(self):
        anime_type=TypeOfWork.objects.create(wikidata_id='Q63952888')
        existing=Movie.objects.create(wikidata_id='Q2001',imdb_id='tt2001',name='Manual anime',type_of_work=anime_type,cover_url='https://example.org/manual.png',rate=9)
        FixtureAPI.items[('tv',1)]['genres']=[{'id':16}]
        FixtureAPI.items[('tv',1)]['keywords']={'results':[{'id':210024}]}
        FixtureAPI.documents['Q2001']['claims']['P31']=[statement({'id':'Q63952888'})]
        self.run_import()
        existing.refresh_from_db()
        self.assertEqual(Movie.objects.count(),1)
        self.assertEqual(existing.type_of_work,anime_type)
        self.assertEqual((existing.name,existing.cover_url,str(existing.rate)),('Manual anime','https://example.org/manual.png','9.0'))
        self.assertEqual(self.report()['created_in_campaign'],0)

    def test_season_episode_character_and_conflicting_movie_format_are_rejected(self):
        for qid in ('Q3464665','Q21191270','Q95074','Q11424'):
            with self.subTest(qid=qid):
                FixtureAPI.documents['Q2001']['claims']['P31']=[statement({'id':qid})]
                self.run_import(directory=self.root/qid)
                self.assertFalse(Movie.objects.exists())
                self.assertEqual(self.report(directory=self.root/qid)['campaign_state']['skips_by_reason'], {'invalid_format':1})

    def test_movie_and_tv_numeric_ids_do_not_collide_and_movie_type_is_specific(self):
        self.run_import()
        self.run_import('import_country_movies')
        self.assertEqual(Movie.objects.count(),2)
        self.assertEqual(Movie.objects.get(wikidata_id='Q1001').type_of_work.wikidata_id,'Q24862')
        self.assertEqual(self.report('import_country_movies')['created_in_campaign'],1)
        self.assertTrue(any(url.endswith('/movie/1') for url,_ in FixtureAPI.requests))

    def test_wrong_tv_identifier_is_rejected(self):
        FixtureAPI.documents['Q2001']['claims']['P4983']=[statement('2')]
        self.run_import()
        self.assertFalse(Movie.objects.exists())
        self.assertEqual(self.skip_reason(),{'identity_conflict':1})

    def test_no_wikidata_and_ambiguous_identity_have_distinct_reasons(self):
        FixtureAPI.items[('tv',1)]['external_ids']={}
        self.run_import()
        self.assertEqual(self.skip_reason(),{'no_wikidata_match':1})
        FixtureAPI.items[('tv',1)]['external_ids']={'wikidata_id':'Q2001'}
        FixtureAPI.documents['Q2001']['claims']['P345'].append(statement('tt9999'))
        self.run_import(retry_skipped=True,refresh_cache=True)
        self.assertEqual(self.skip_reason(),{'ambiguous_identity':1})
        self.assertFalse(Movie.objects.exists())

    def test_each_production_country_and_original_language_does_not_filter_ukrainian_movie(self):
        for iso,qid in (('RU','Q159'),('UA','Q212'),('KZ','Q232')):
            with self.subTest(iso=iso):
                FixtureAPI.items[('movie',1)].update(production_countries=[{'iso_3166_1':iso}],origin_country=[iso],original_language='ru')
                FixtureAPI.documents['Q1001']['claims']['P495']=[statement({'id':qid})]
                directory=self.root/iso
                self.run_import('import_country_movies',countries=iso,directory=directory)
                movie=Movie.objects.get()
                self.assertEqual(set(movie.countries.values_list('wikidata_id',flat=True)),{qid})
                Movie.objects.all().delete()

    def test_or_selection_coproduction_and_priority_pass_deduplication(self):
        FixtureAPI.items[('movie',1)].update(production_countries=[{'iso_3166_1':'RU'},{'iso_3166_1':'UA'}],origin_country=['RU','UA'])
        FixtureAPI.documents['Q1001']['claims']['P495']=[statement({'id':'Q159'}),statement({'id':'Q212'})]
        self.run_import('import_country_movies',countries='UA,RU')
        self.assertEqual(Movie.objects.count(),1)
        self.assertEqual(Movie.objects.get().countries.count(),2)
        self.assertEqual(self.report('import_country_movies')['run']['examined'],1)

    def test_broad_pass_finds_production_country_missing_from_origin_country(self):
        FixtureAPI.items[('movie',1)]['origin_country']=['US']
        self.run_import('import_country_movies',countries='RU')
        self.assertEqual(Movie.objects.count(),1)
        self.assertTrue(any(params.get('with_origin_country')=='RU' for _,params in FixtureAPI.requests))
        self.assertTrue(any('/discover/movie' in url and 'with_origin_country' not in params for url,params in FixtureAPI.requests))

    def test_original_russian_language_and_successor_origin_do_not_include_us_or_ussr(self):
        for country in ('US','SU'):
            with self.subTest(country=country):
                FixtureAPI.items[('movie',1)].update(production_countries=[{'iso_3166_1':country}],origin_country=['RU'],original_language='ru')
                directory=self.root/country
                self.run_import('import_country_movies',directory=directory)
                self.assertEqual(self.report('import_country_movies',directory)['campaign_state']['skips_by_reason'],{'outside_countries':1})
                self.assertFalse(Movie.objects.exists())

    def test_conflicting_wikidata_country_skips_before_writes(self):
        FixtureAPI.documents['Q1001']['claims']['P495']=[statement({'id':'Q30'})]
        self.run_import('import_country_movies')
        self.assertEqual(self.skip_reason('import_country_movies'),{'country_conflict':1})
        self.assertFalse(Movie.objects.exists())
        self.assertFalse(Country.objects.exists())

    def test_manual_country_conflict_does_not_change_filled_fields_or_relations(self):
        movie=Movie.objects.create(wikidata_id='Q1001',name='Hand filled',description='Keep',year=1980)
        country=Country.objects.create(wikidata_id='Q30');movie.countries.add(country)
        self.run_import('import_country_movies')
        movie.refresh_from_db()
        self.assertEqual((movie.name,movie.description,movie.year),('Hand filled','Keep',1980))
        self.assertEqual(list(movie.countries.all()),[country])
        self.assertEqual(self.skip_reason('import_country_movies'),{'country_conflict':1})

    def test_missing_russian_translation_poster_and_votes_do_not_prevent_import(self):
        item=FixtureAPI.items[('tv',1)]
        item['translations']={'translations':[]};item['poster_path']=None
        FixtureAPI.documents['Q2001']['labels']={'en':{'value':'English title'}}
        self.run_import()
        movie=Movie.objects.get()
        self.assertFalse(movie.translations.filter(language_code='ru').exists())
        self.assertEqual(movie.cover_url,'')

    def test_dry_run_preserves_all_models_and_real_queue_then_apply_resumes(self):
        with patch.object(animation,'refresh_movie_documents') as index:
            self.run_import(dry_run=True,max_candidates=1)
            index.assert_not_called()
        self.assertFalse(Movie.objects.exists());self.assertFalse(TypeOfWork.objects.exists())
        self.assertEqual(self.report()['campaign_state']['dry_run'],{'would_create':1})
        self.assertEqual(self.report()['created_in_campaign'],0)
        self.run_import(max_candidates=1)
        self.assertEqual(Movie.objects.count(),1)
        self.assertEqual(self.report()['created_in_campaign'],1)

    def test_target_resume_does_not_lose_page_remainder_or_count_existing(self):
        FixtureAPI.items[('tv',2)]=detail('tv',2)
        FixtureAPI.documents['Q2002']=entity('Q2002',P31=['Q5398426'],P4983=['2'],P345=['tt2002'])
        self.run_import(target_new=1)
        self.assertEqual(Movie.objects.count(),1)
        self.run_import(target_new=2)
        self.assertEqual(Movie.objects.count(),2)
        self.assertEqual(self.report()['created_in_campaign'],2)
        self.run_import(directory=self.root/'fresh')
        self.assertEqual(Movie.objects.count(),2)
        self.assertEqual(self.report(directory=self.root/'fresh')['created_in_campaign'],0)

    def test_retry_skipped_does_not_recount_or_revisit_created(self):
        FixtureAPI.items[('tv',1)]['adult']=True
        self.run_import()
        FixtureAPI.items[('tv',1)]['adult']=False
        self.run_import(retry_skipped=True,refresh_cache=True)
        self.assertEqual(Movie.objects.count(),1)
        self.assertEqual(self.report()['created_in_campaign'],1)
        self.run_import(retry_skipped=True)
        self.assertEqual(self.report()['run'].get('examined',0),0)

    def test_incompatible_filters_fail_before_any_state_write(self):
        self.run_import('import_country_movies',countries='RU')
        path=self.root/'import_country_movies'/'state.sqlite3';before=path.read_bytes()
        with self.assertRaises(CommandError):
            self.run_import('import_country_movies',countries='KZ')
        self.assertEqual(path.read_bytes(),before)

    def test_temporary_api_failure_keeps_candidate_pending_for_resume(self):
        with patch.object(FixtureAPI, 'details', side_effect=CommandError('temporary fixture API failure')):
            with self.assertRaisesMessage(CommandError, 'temporary fixture API failure'):
                self.run_import()
        self.assertEqual(self.report()['status'], 'failed')
        self.assertEqual(self.report()['campaign_state']['candidates'], {'pending':1})
        self.assertFalse(Movie.objects.exists())
        self.run_import()
        self.assertEqual(Movie.objects.count(), 1)
        self.assertEqual(self.report()['created_in_campaign'], 1)


@skipUnless(connection.vendor == 'postgresql', 'Real shared writer locks require isolated PostgreSQL')
class CatalogueTransactionsTests(ImportFixtures, TransactionTestCase):
    def test_network_is_outside_transactions_and_cross_directory_lock_fails_fast(self):
        import psycopg
        FixtureAPI.require_outside_atomic=True
        self.run_import(max_candidates=1)
        self.run_import('import_country_movies', max_candidates=1)
        params=connection.get_connection_params()
        other=psycopg.connect(**params);other.autocommit=True
        try:
            other.execute('SELECT pg_advisory_lock(%s)',[704913204817])
            with self.assertRaisesMessage(CommandError,'Другой импорт RAFS'):
                self.run_import(directory=self.root/'blocked')
            self.assertFalse((self.root/'blocked'/'state.sqlite3').exists())
        finally:
            other.close()
