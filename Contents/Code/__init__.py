import bridge
from ss import Downloader, DownloadStatus, Wizard, cache, util

#util.redirect_output('/Users/mike/Work/other/ss-plex.bundle/out')

PLUGIN_PREFIX = '/video/ssp'
PLUGIN_TITLE  = L('title')
PLUGIN_ART    = 'art-default.jpg'
PLUGIN_ICON   = 'icon-default.png'

to_export = dict(Log = Log, Dict = Dict, XML = XML, HTML = HTML, JSON = JSON, Prefs = Prefs)
bridge.plex.init(**to_export)

def Start():
    # Initialize the plug-in
    Plugin.AddViewGroup('Details',  viewMode = 'InfoList',  mediaType = 'items')
    Plugin.AddViewGroup('List',     viewMode = 'List',      mediaType = 'items')

    ObjectContainer.view_group = 'List'
    ObjectContainer.art        = R(PLUGIN_ART)
    DirectoryObject.art        = R(PLUGIN_ART)
    Log('"Starting" SS-Plex')

def ValidatePrefs(): pass

@handler(PLUGIN_PREFIX, PLUGIN_TITLE, thumb = PLUGIN_ICON, art = PLUGIN_ART)
def MainMenu():
    container = render_listings('/')

    container.add(button('heading.favorites',    FavoritesIndex, icon = 'icon-favorites.png'))
    container.add(input_button('heading.search', 'search.prompt', SearchResults, icon = 'icon-search.png', foo = 1))
    container.add(button('search.heading.saved', SearchIndex, icon = 'icon-saved-search.png'))
    container.add(button('heading.download',     DownloadsIndex, refresh = 0, icon = 'icon-downloads.png'))
    container.add(button('heading.system',       SystemIndex, icon = 'icon-system.png'))

    return container

##########
# System #
##########

@route('%s/system' % PLUGIN_PREFIX)
def SystemIndex():
    container = ObjectContainer(title1 = L('heading.system'))

    container.add(PrefsObject(title = L('system.heading.preferences')))
    container.add(confirm('system.heading.reset-favorites',        SystemConfirmResetFavorites))
    container.add(confirm('system.heading.reset-search',           SystemConfirmResetSearches))
    container.add(confirm('system.heading.reset-download-history', SystemConfirmResetDownloads))
    container.add(confirm('system.heading.reset-factory',          SystemConfirmResetFactory))
    container.add(button('system.heading.dispatch-force',          DownloadsDispatchForce))
    container.add(button('version %s' % util.version.string, SystemIndex))

    return container

@route('%s/system/confirm/reset-favorites' % PLUGIN_PREFIX)
def SystemConfirmResetFavorites(): return warning('system.warning.reset-favorites', 'confirm.yes', SystemResetFavorites)

@route('%s/system/confirm/reset-searches' % PLUGIN_PREFIX)
def SystemConfirmResetSearches(): return warning('system.warning.reset-search', 'confirm.yes', SystemResetSearches)

@route('%s/system/confirm/reset-downloads' % PLUGIN_PREFIX)
def SystemConfirmResetDownloads(): return warning('system.warning.reset-download-history', 'confirm.yes', SystemResetDownloads)

@route('%s/system/confirm/reset-factory' % PLUGIN_PREFIX)
def SystemConfirmResetFactory(): return warning('system.warning.reset-factory', 'confirm.yes', SystemResetFactory)

@route('%s/system/reset/favorites' % PLUGIN_PREFIX)
def SystemResetFavorites():
    bridge.favorite.clear()
    return dialog('heading.system', 'system.response.reset-favorites')

@route('%s/system/reset/searches' % PLUGIN_PREFIX)
def SystemResetSearches():
    bridge.search.clear()
    return dialog('heading.system', 'system.response.reset-search')

@route('%s/system/reset/downloads' % PLUGIN_PREFIX)
def SystemResetDownloads():
    bridge.download.clear_history()
    return dialog('heading.system', 'system.response.reset-download-history')

@route('%s/system/reset/factory' % PLUGIN_PREFIX)
def SystemResetFactory():
    Dict.Reset()
    return dialog('heading.system', 'system.response.reset-factory')

#############
# Searching #
#############

@route('%s/search' % PLUGIN_PREFIX)
def SearchIndex():
    container = ObjectContainer()

    for query in util.sorted_by_title(bridge.search.collection()):
        container.add(button(query, SearchResults, query = query, foo = 1))

    return container

#@route('%s/search/results/{query}' % PLUGIN_PREFIX)
def SearchResults(query, foo):
    container = render_listings('/search/%s' % util.q(query))
    labels    = [ 'add', 'remove' ]
    response  = int(bridge.search.includes(query))

    container.objects.insert(0, button('search.heading.%s' % labels[response], SearchToggle, query = query))
    return container

@route('%s/search/toggle' % PLUGIN_PREFIX)
def SearchToggle(query):
    message = 'search.response.%s' % bridge.search.toggle(query)
    return dialog('heading.search', message)

#############
# Favorites #
#############

@route('%s/favorites' % PLUGIN_PREFIX)
def FavoritesIndex():
    container = ObjectContainer(
        title1 = 'Favorites'
    )

    if 'favorites' in Dict:
        container.add(button('favorites.heading.migrate', FavoritesMigrate1to2))
    else:
        for endpoint, fav in util.sorted_by_title(bridge.favorite.collection().iteritems(), lambda x: x[1]['title']):
            title  = fav['title']
            native = TVShowObject(
                rating_key = endpoint,
                title      = title,
                thumb      = fav['artwork'],
                key        = Callback(ListTVShow, refresh = 0, endpoint = endpoint, show_title = title)
            )

            container.add(native)

    return container

@route('%s/favorites/toggle' % PLUGIN_PREFIX)
def FavoritesToggle(endpoint, show_title, artwork):
    message = None

    if bridge.favorite.includes(endpoint):
        message = 'favorites.response.removed'
        bridge.favorite.remove(endpoint)
    else:
        message = 'favorites.response.added'
        bridge.favorite.append(endpoint = endpoint, title = show_title, artwork = artwork)

    return dialog('heading.favorites', F(message, show_title))

def FavoritesMigrate1to2():
    @thread
    def migrate():
        if 'favorites' in Dict:
            old_favorites = bridge.plex.user_dict()['favorites']
            new_favorites = bridge.favorite.collection()

            for endpoint, title in old_favorites.iteritems():
                if endpoint not in new_favorites:
                    try:
                        response = JSON.ObjectFromURL(util.listings_endpoint(endpoint))
                        bridge.favorite.append(endpoint = endpoint, title = response['display_title'], artwork = response['artwork'])
                    except Exception, e:
                        #util.print_exception(e)
                        pass

            del Dict['favorites']
            bridge.plex.user_dict().Save()

    migrate()
    return dialog('Favorites', 'Your favorites are being updated. Return shortly.')

###############
# Downloading #
###############

@route('%s/downloads/i{refresh}' % PLUGIN_PREFIX)
def DownloadsIndex(refresh = 0):
    container = ObjectContainer(title1 = L('heading.download'))

    if bridge.download.assumed_running():
        current       = bridge.download.current()
        endpoint      = current['endpoint']
        status        = DownloadStatus(Downloader.status_file_for(endpoint))

        container.add(popup_button(current['title'], DownloadsOptions, endpoint = endpoint, icon = 'icon-downloads.png'))

        for ln in status.report():
            container.add(popup_button(ln, DownloadsOptions, endpoint = endpoint, icon = 'icon-downloads.png'))

    for download in bridge.download.queue():
        container.add(popup_button(download['title'], DownloadsOptions, endpoint = download['endpoint'], icon = 'icon-downloads-queue.png'))

    add_refresh_to(container, refresh, DownloadsIndex)
    return container

@route('%s/downloads/show' % PLUGIN_PREFIX)
def DownloadsOptions(endpoint):
    download = bridge.download.from_queue(endpoint)

    if download:
        container  = ObjectContainer(title1 = download['title'])
        obj_cancel = button('download.heading.cancel', DownloadsCancel, endpoint = endpoint)

        if bridge.download.assumed_running():
            if bridge.download.curl_running():
                container.add(button('download.heading.next', DownloadsNext))
                container.add(obj_cancel)
            else:
                container.add(button('download.heading.repair', DownloadsDispatchForce))
        else:
            container.add(obj_cancel)

        return container
    else:
        return dialog('heading.error', F('download.response.not-found', endpoint))

@route('%s/downloads/queue' % PLUGIN_PREFIX)
def DownloadsQueue(endpoint, media_hint, title):
    if bridge.download.in_history(endpoint):
        message = 'exists'
    else:
        message = 'added'
        bridge.download.append(title = title, endpoint = endpoint, media_hint = media_hint)

    dispatch_download_threaded()
    return dialog('heading.download', F('download.response.%s' % message, title))

@route('%s/downloads/dispatch' % PLUGIN_PREFIX)
def DownloadsDispatch():
    dispatch_download_threaded()

@route('%s/downloads/dispatch/force' % PLUGIN_PREFIX)
def DownloadsDispatchForce():
    bridge.download.clear_current()
    dispatch_download_threaded()

@route('%s/downloads/cancel' % PLUGIN_PREFIX)
def DownloadsCancel(endpoint):
    download = bridge.download.from_queue(endpoint)

    if download:
        if bridge.download.is_current(endpoint):
            bridge.download.command('cancel')
        else:
            try:
                bridge.download.remove(download)
            except Exception, e:
                #util.print_exception(e)
                pass

        return dialog('heading.download', F('download.response.cancel', download['title']))
    else:
        return dialog('heading.error', F('download.response.not-found', endpoint))

@route('%s/downloads/next' % PLUGIN_PREFIX)
def DownloadsNext():
    bridge.download.command('next')

#########################
# Development Endpoints #
#########################

@route('%s/test' % PLUGIN_PREFIX)
def QuickTest():
    def test_cache():
        return 'foo'

    return ObjectContainer(header = 'Test', message = cache_fetch('test', test_cache))

# UAS
@route('%s/update' % PLUGIN_PREFIX)
def UASUpdate():
    import uas
    return uas.updater.check(id = 'SS Plex', Dict = Dict, ObjectContainer = ObjectContainer)

###################
# Listing Methods #
###################

@route('%s/RenderListings' % PLUGIN_PREFIX)
def RenderListings(endpoint, default_title = None):
    return render_listings(endpoint, default_title)

@route('%s/WatchOptions' % PLUGIN_PREFIX)
def WatchOptions(endpoint, title, media_hint):
    container    = render_listings(endpoint, default_title = title, cache_time = cache.TIME_DAY)
    wizard_url   = '//ss/wizard?endpoint=%s&avoid_flv=%s' % (endpoint, int(bridge.user.avoid_flv_streaming()))
    wizard_item  = VideoClipObject(title = L('media.watch-now'), url = wizard_url)
    sources_item = button('media.all-sources', ListSources, endpoint = endpoint, title = title)

    if bridge.download.in_history(endpoint):
        download_item = button('media.persisted', DownloadsOptions, endpoint = endpoint)
    else:
        download_item = button('media.watch-later', DownloadsQueue,
            endpoint   = endpoint,
            media_hint = media_hint,
            title      = title
        )

    container.objects.insert(0, wizard_item)
    container.objects.insert(1, download_item)
    container.objects.insert(2, sources_item)

    return container

@route('%s/ListSources' % PLUGIN_PREFIX)
def ListSources(endpoint, title):
    wizard = Wizard(endpoint, environment = bridge.environment.plex)
    return render_listings_response(wizard.payload, endpoint)

@route('%s/series/i{refresh}' % PLUGIN_PREFIX)
def ListTVShow(endpoint, show_title, refresh = 0):
    container, response = render_listings(endpoint + '/episodes', show_title, True)
    labels   = [ 'add', 'remove' ]
    label    = labels[int(bridge.favorite.includes(endpoint))]

    container.objects.insert(0, button('favorites.heading.%s' % label, FavoritesToggle,
        endpoint   = endpoint,
        icon       = 'icon-favorites.png',
        show_title = show_title,
        artwork    = response['resource']['artwork']
    ))

    add_refresh_to(container, refresh, ListTVShow,
        endpoint   = endpoint,
        show_title = show_title,
    )

    return container

def render_listings(endpoint, default_title = None, return_response = False, cache_time = None):
    listings_endpoint = util.listings_endpoint(endpoint)

    response  = JSON.ObjectFromURL(listings_endpoint, cacheTime = cache_time)
    container = render_listings_response(response, endpoint = endpoint, default_title = default_title)

    if return_response:
        return [ container, response ]
    else:
        return container

def render_listings_response(response, endpoint, default_title = None):
    container = ObjectContainer(
        title1 = response.get('title') or default_title,
        title2 = response.get('desc')
    )

    for element in response.get( 'items', [] ):
        native          = None
        permalink        = element.get('endpoint')
        display_title    = element.get('display_title')    or element.get('title')
        overview         = element.get('display_overview') or element.get('overview')
        tagline          = element.get('display_tagline')  or element.get('tagline')
        element_type     = element.get('_type')
        generic_callback = Callback(RenderListings, endpoint = permalink, default_title = display_title)

        if 'endpoint' == element_type:
            native = DirectoryObject(
                title   = display_title,
                tagline = tagline,
                summary = overview,
                key     = generic_callback,
                thumb   = element.get('artwork')
            )

            if '/' == endpoint:
                if 'tv' in display_title.lower():
                    native.thumb = R('icon-tv.png')
                elif 'movie' in display_title.lower():
                    native.thumb = R('icon-movies.png')

        elif 'show' == element_type:
            native = TVShowObject(
                rating_key = permalink,
                title      = display_title,
                summary    = overview,
                thumb      = element.get('artwork'),
                key        = Callback(ListTVShow, refresh = 0, endpoint = permalink, show_title = display_title)
            )

        elif 'movie' == element_type or 'episode' == element_type:
            media_hint = element_type
            if 'episode' == media_hint:
                media_hint = 'show'

            native = PopupDirectoryObject(
                title   = display_title,
                tagline = tagline,
                thumb   = element.get('artwork'),
                summary = overview,
                key     = Callback(WatchOptions, endpoint = permalink, title = display_title, media_hint = media_hint)
            )

        elif 'foreign' == element_type:
            final_url = element.get('final_url')

            if final_url:
                service_url = '//ss/procedure?url=%s' % util.q(final_url)
            else:
                service_url = '//ss%s' % util.translate_endpoint(element['original_url'], element['foreign_url'], True)

            native = VideoClipObject(title = element['domain'], url = service_url)

        #elif 'final' == element_type:
            #ss_url = '//ss/procedure?url=%s&title=%s' % (util.q(element['url']), util.q('FILE HINT HERE'))
            #native = VideoClipObject(url = ss_url, title = display_title)

        #elif 'movie' == element_type:
            #native = MovieObject(
                #rating_key = permalink,
                #title      = display_title,
                #tagline    = element.get( 'tagline' ),
                #summary    = element.get( 'desc' ),
                #key        = sources_callback
            #)
        #elif 'episode' == element_type:
            #native = EpisodeObject(
                #rating_key     = permalink,
                #title          = display_title,
                #summary        = element.get( 'desc' ),
                #season         = int( element.get( 'season', 0 ) ),
                #absolute_index = int( element.get( 'number', 0 ) ),
                #key            = sources_callback
            #)

        if None != native:
            container.add( native )

    return container

##################
# Plugin Helpers #
##################

def dialog(title, message):           return ObjectContainer(header = L(str(title)), message = L(str(message)))
def confirm(otitle, ocb, **kwargs):   return popup_button(L(str(otitle)), ocb, **kwargs)
def warning(otitle, ohandle, ocb, **kwargs):
    container = ObjectContainer(header = L(str(otitle)))
    container.add(button(L(str(ohandle)), ocb, **kwargs))

    return container

def plobj(obj, otitle, cb, **kwargs):
    icon = None

    if 'icon' in kwargs:
        icon = R(kwargs['icon'])
        del kwargs['icon']

    item = obj(title = otitle, key = Callback(cb, **kwargs))
    if icon:
        item.thumb = icon

    return item

def button(otitle, ocb, **kwargs):       return plobj(DirectoryObject,      L(str(otitle)), ocb, **kwargs)
def popup_button(otitle, ocb, **kwargs): return plobj(PopupDirectoryObject, L(str(otitle)), ocb, **kwargs)
def input_button(otitle, prompt, ocb, **kwargs):
    item        = plobj(InputDirectoryObject, L(str(otitle)), ocb, **kwargs)
    item.prompt = L(str(prompt))
    return item

def dispatch_download_threaded():
    bridge.download.dispatch()

def add_refresh_to(container, refresh, ocb, **kwargs):
    refresh           = int(refresh)
    kwargs['refresh'] = refresh + 1
    kwargs['icon']    = 'icon-refresh.png'

    if 0 < refresh:
        container.replace_parent = True

    container.add(button('heading.refresh', ocb, **kwargs))

    return container
