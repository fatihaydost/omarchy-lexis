.pragma library

// Singleton Service.qml ile monitör başına oluşturulan BarWidget.qml örnekleri
// arasındaki süreç içi köprü.

var service = null
var _listeners = []
var _barWidgets = []

function registerService(svc) {
  service = svc
  for (var i = 0; i < _listeners.length; i++) {
    try { _listeners[i](svc) } catch (e) {}
  }
}

function unregisterService(svc) {
  if (service === svc) {
    service = null
    for (var i = 0; i < _listeners.length; i++) {
      try { _listeners[i](null) } catch (e) {}
    }
  }
}

function subscribe(fn) {
  if (_listeners.indexOf(fn) === -1) _listeners.push(fn)
  if (service) {
    try { fn(service) } catch (e) {}
  }
}

function unsubscribe(fn) {
  var idx = _listeners.indexOf(fn)
  if (idx !== -1) _listeners.splice(idx, 1)
}

function registerBarWidget(w) {
  if (_barWidgets.indexOf(w) === -1) _barWidgets.push(w)
}

function unregisterBarWidget(w) {
  var idx = _barWidgets.indexOf(w)
  if (idx !== -1) _barWidgets.splice(idx, 1)
}

function barWidgetForScreen(screenName) {
  for (var i = 0; i < _barWidgets.length; i++) {
    var w = _barWidgets[i]
    if (!w) continue
    if (screenName && w.screenName === screenName) return w
  }
  return _barWidgets.length > 0 ? _barWidgets[0] : null
}

function windowScreenName(winObj) {
  if (!winObj) return ""
  var scr = winObj.screen
  return (scr && scr.name) ? String(scr.name) : ""
}
