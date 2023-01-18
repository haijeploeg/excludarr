(function(f) {
  if (typeof exports === "object" && typeof module !== "undefined") {
      module.exports = f()
  } else if (typeof define === "function" && define.amd) {
      define([], f)
  } else {
      var g;
      if (typeof window !== "undefined") {
          g = window
      } else if (typeof global !== "undefined") {
          g = global
      } else if (typeof self !== "undefined") {
          g = self
      } else {
          g = this
      }
      g.simpleDatatables = f()
  }
})(function() {
  var define,
      module,
      exports;
  return (function() {
      function r(e, n, t) {
          function o(i, f) {
              if (!n[i]) {
                  if (!e[i]) {
                      var c = "function" == typeof require && require;
                      if (!f && c)
                          return c(i, !0);
                      if (u)
                          return u(i, !0);
                      var a = new Error("Cannot find module '" + i + "'");
                      throw a.code = "MODULE_NOT_FOUND", a
                  }
                  var p = n[i] = {
                      exports: {}
                  };
                  e[i][0].call(p.exports, function(r) {
                      var n = e[i][1][r];
                      return o(n || r)
                  }, p, p.exports, r, e, n, t)
              }
              return n[i].exports
          }
          for (var u = "function" == typeof require && require, i = 0; i < t.length; i++)
              o(t[i]);
          return o
      }
      return r
  })()({
      1: [function(require, module, exports) {
          (function(global) {
              (function() {
                  "use strict";
                  "undefined" != typeof globalThis ? globalThis : "undefined" != typeof window ? window : "undefined" != typeof global ? global : "undefined" != typeof self && self;
                  function t(t, e) {
                      return t(e = {
                          exports: {}
                      }, e.exports), e.exports
                  }
                  var e = t((function(t, e) {
                          t.exports = function() {
                              var t = "millisecond",
                                  e = "second",
                                  n = "minute",
                                  r = "hour",
                                  i = "day",
                                  s = "week",
                                  a = "month",
                                  o = "quarter",
                                  u = "year",
                                  f = "date",
                                  h = /^(\d{4})[-/]?(\d{1,2})?[-/]?(\d{0,2})[^0-9]*(\d{1,2})?:?(\d{1,2})?:?(\d{1,2})?[.:]?(\d+)?$/,
                                  c = /\[([^\]]+)]|Y{1,4}|M{1,4}|D{1,2}|d{1,4}|H{1,2}|h{1,2}|a|A|m{1,2}|s{1,2}|Z{1,2}|SSS/g,
                                  d = {
                                      name: "en",
                                      weekdays: "Sunday_Monday_Tuesday_Wednesday_Thursday_Friday_Saturday".split("_"),
                                      months: "January_February_March_April_May_June_July_August_September_October_November_December".split("_")
                                  },
                                  l = function(t, e, n) {
                                      var r = String(t);
                                      return !r || r.length >= e ? t : "" + Array(e + 1 - r.length).join(n) + t
                                  },
                                  M = {
                                      s: l,
                                      z: function(t) {
                                          var e = -t.utcOffset(),
                                              n = Math.abs(e),
                                              r = Math.floor(n / 60),
                                              i = n % 60;
                                          return (e <= 0 ? "+" : "-") + l(r, 2, "0") + ":" + l(i, 2, "0")
                                      },
                                      m: function t(e, n) {
                                          if (e.date() < n.date())
                                              return -t(n, e);
                                          var r = 12 * (n.year() - e.year()) + (n.month() - e.month()),
                                              i = e.clone().add(r, a),
                                              s = n - i < 0,
                                              o = e.clone().add(r + (s ? -1 : 1), a);
                                          return +(-(r + (n - i) / (s ? i - o : o - i)) || 0)
                                      },
                                      a: function(t) {
                                          return t < 0 ? Math.ceil(t) || 0 : Math.floor(t)
                                      },
                                      p: function(h) {
                                          return {
                                                  M: a,
                                                  y: u,
                                                  w: s,
                                                  d: i,
                                                  D: f,
                                                  h: r,
                                                  m: n,
                                                  s: e,
                                                  ms: t,
                                                  Q: o
                                              }[h] || String(h || "").toLowerCase().replace(/s$/, "")
                                      },
                                      u: function(t) {
                                          return void 0 === t
                                      }
                                  },
                                  $ = "en",
                                  m = {};
                              m[$] = d;
                              var D = function(t) {
                                      return t instanceof y
                                  },
                                  Y = function(t, e, n) {
                                      var r;
                                      if (!t)
                                          return $;
                                      if ("string" == typeof t)
                                          m[t] && (r = t),
                                          e && (m[t] = e, r = t);
                                      else {
                                          var i = t.name;
                                          m[i] = t,
                                          r = i
                                      }
                                      return !n && r && ($ = r), r || !n && $
                                  },
                                  v = function(t, e) {
                                      if (D(t))
                                          return t.clone();
                                      var n = "object" == typeof e ? e : {};
                                      return n.date = t, n.args = arguments, new y(n)
                                  },
                                  p = M;
                              p.l = Y,
                              p.i = D,
                              p.w = function(t, e) {
                                  return v(t, {
                                      locale: e.$L,
                                      utc: e.$u,
                                      x: e.$x,
                                      $offset: e.$offset
                                  })
                              };
                              var y = function() {
                                      function d(t) {
                                          this.$L = Y(t.locale, null, !0),
                                          this.parse(t)
                                      }
                                      var l = d.prototype;
                                      return l.parse = function(t) {
                                          this.$d = function(t) {
                                              var e = t.date,
                                                  n = t.utc;
                                              if (null === e)
                                                  return new Date(NaN);
                                              if (p.u(e))
                                                  return new Date;
                                              if (e instanceof Date)
                                                  return new Date(e);
                                              if ("string" == typeof e && !/Z$/i.test(e)) {
                                                  var r = e.match(h);
                                                  if (r) {
                                                      var i = r[2] - 1 || 0,
                                                          s = (r[7] || "0").substring(0, 3);
                                                      return n ? new Date(Date.UTC(r[1], i, r[3] || 1, r[4] || 0, r[5] || 0, r[6] || 0, s)) : new Date(r[1], i, r[3] || 1, r[4] || 0, r[5] || 0, r[6] || 0, s)
                                                  }
                                              }
                                              return new Date(e)
                                          }(t),
                                          this.$x = t.x || {},
                                          this.init()
                                      }, l.init = function() {
                                          var t = this.$d;
                                          this.$y = t.getFullYear(),
                                          this.$M = t.getMonth(),
                                          this.$D = t.getDate(),
                                          this.$W = t.getDay(),
                                          this.$H = t.getHours(),
                                          this.$m = t.getMinutes(),
                                          this.$s = t.getSeconds(),
                                          this.$ms = t.getMilliseconds()
                                      }, l.$utils = function() {
                                          return p
                                      }, l.isValid = function() {
                                          return !("Invalid Date" === this.$d.toString())
                                      }, l.isSame = function(t, e) {
                                          var n = v(t);
                                          return this.startOf(e) <= n && n <= this.endOf(e)
                                      }, l.isAfter = function(t, e) {
                                          return v(t) < this.startOf(e)
                                      }, l.isBefore = function(t, e) {
                                          return this.endOf(e) < v(t)
                                      }, l.$g = function(t, e, n) {
                                          return p.u(t) ? this[e] : this.set(n, t)
                                      }, l.unix = function() {
                                          return Math.floor(this.valueOf() / 1e3)
                                      }, l.valueOf = function() {
                                          return this.$d.getTime()
                                      }, l.startOf = function(t, o) {
                                          var h = this,
                                              c = !!p.u(o) || o,
                                              d = p.p(t),
                                              l = function(t, e) {
                                                  var n = p.w(h.$u ? Date.UTC(h.$y, e, t) : new Date(h.$y, e, t), h);
                                                  return c ? n : n.endOf(i)
                                              },
                                              M = function(t, e) {
                                                  return p.w(h.toDate()[t].apply(h.toDate("s"), (c ? [0, 0, 0, 0] : [23, 59, 59, 999]).slice(e)), h)
                                              },
                                              $ = this.$W,
                                              m = this.$M,
                                              D = this.$D,
                                              Y = "set" + (this.$u ? "UTC" : "");
                                          switch (d) {
                                          case u:
                                              return c ? l(1, 0) : l(31, 11);
                                          case a:
                                              return c ? l(1, m) : l(0, m + 1);
                                          case s:
                                              var v = this.$locale().weekStart || 0,
                                                  y = ($ < v ? $ + 7 : $) - v;
                                              return l(c ? D - y : D + (6 - y), m);
                                          case i:
                                          case f:
                                              return M(Y + "Hours", 0);
                                          case r:
                                              return M(Y + "Minutes", 1);
                                          case n:
                                              return M(Y + "Seconds", 2);
                                          case e:
                                              return M(Y + "Milliseconds", 3);
                                          default:
                                              return this.clone()
                                          }
                                      }, l.endOf = function(t) {
                                          return this.startOf(t, !1)
                                      }, l.$set = function(s, o) {
                                          var h,
                                              c = p.p(s),
                                              d = "set" + (this.$u ? "UTC" : ""),
                                              l = (h = {}, h[i] = d + "Date", h[f] = d + "Date", h[a] = d + "Month", h[u] = d + "FullYear", h[r] = d + "Hours", h[n] = d + "Minutes", h[e] = d + "Seconds", h[t] = d + "Milliseconds", h)[c],
                                              M = c === i ? this.$D + (o - this.$W) : o;
                                          if (c === a || c === u) {
                                              var $ = this.clone().set(f, 1);
                                              $.$d[l](M),
                                              $.init(),
                                              this.$d = $.set(f, Math.min(this.$D, $.daysInMonth())).$d
                                          } else
                                              l && this.$d[l](M);
                                          return this.init(), this
                                      }, l.set = function(t, e) {
                                          return this.clone().$set(t, e)
                                      }, l.get = function(t) {
                                          return this[p.p(t)]()
                                      }, l.add = function(t, o) {
                                          var f,
                                              h = this;
                                          t = Number(t);
                                          var c = p.p(o),
                                              d = function(e) {
                                                  var n = v(h);
                                                  return p.w(n.date(n.date() + Math.round(e * t)), h)
                                              };
                                          if (c === a)
                                              return this.set(a, this.$M + t);
                                          if (c === u)
                                              return this.set(u, this.$y + t);
                                          if (c === i)
                                              return d(1);
                                          if (c === s)
                                              return d(7);
                                          var l = (f = {}, f[n] = 6e4, f[r] = 36e5, f[e] = 1e3, f)[c] || 1,
                                              M = this.$d.getTime() + t * l;
                                          return p.w(M, this)
                                      }, l.subtract = function(t, e) {
                                          return this.add(-1 * t, e)
                                      }, l.format = function(t) {
                                          var e = this;
                                          if (!this.isValid())
                                              return "Invalid Date";
                                          var n = t || "YYYY-MM-DDTHH:mm:ssZ",
                                              r = p.z(this),
                                              i = this.$locale(),
                                              s = this.$H,
                                              a = this.$m,
                                              o = this.$M,
                                              u = i.weekdays,
                                              f = i.months,
                                              h = function(t, r, i, s) {
                                                  return t && (t[r] || t(e, n)) || i[r].substr(0, s)
                                              },
                                              d = function(t) {
                                                  return p.s(s % 12 || 12, t, "0")
                                              },
                                              l = i.meridiem || function(t, e, n) {
                                                  var r = t < 12 ? "AM" : "PM";
                                                  return n ? r.toLowerCase() : r
                                              },
                                              M = {
                                                  YY: String(this.$y).slice(-2),
                                                  YYYY: this.$y,
                                                  M: o + 1,
                                                  MM: p.s(o + 1, 2, "0"),
                                                  MMM: h(i.monthsShort, o, f, 3),
                                                  MMMM: h(f, o),
                                                  D: this.$D,
                                                  DD: p.s(this.$D, 2, "0"),
                                                  d: String(this.$W),
                                                  dd: h(i.weekdaysMin, this.$W, u, 2),
                                                  ddd: h(i.weekdaysShort, this.$W, u, 3),
                                                  dddd: u[this.$W],
                                                  H: String(s),
                                                  HH: p.s(s, 2, "0"),
                                                  h: d(1),
                                                  hh: d(2),
                                                  a: l(s, a, !0),
                                                  A: l(s, a, !1),
                                                  m: String(a),
                                                  mm: p.s(a, 2, "0"),
                                                  s: String(this.$s),
                                                  ss: p.s(this.$s, 2, "0"),
                                                  SSS: p.s(this.$ms, 3, "0"),
                                                  Z: r
                                              };
                                          return n.replace(c, (function(t, e) {
                                              return e || M[t] || r.replace(":", "")
                                          }))
                                      }, l.utcOffset = function() {
                                          return 15 * -Math.round(this.$d.getTimezoneOffset() / 15)
                                      }, l.diff = function(t, f, h) {
                                          var c,
                                              d = p.p(f),
                                              l = v(t),
                                              M = 6e4 * (l.utcOffset() - this.utcOffset()),
                                              $ = this - l,
                                              m = p.m(this, l);
                                          return m = (c = {}, c[u] = m / 12, c[a] = m, c[o] = m / 3, c[s] = ($ - M) / 6048e5, c[i] = ($ - M) / 864e5, c[r] = $ / 36e5, c[n] = $ / 6e4, c[e] = $ / 1e3, c)[d] || $, h ? m : p.a(m)
                                      }, l.daysInMonth = function() {
                                          return this.endOf(a).$D
                                      }, l.$locale = function() {
                                          return m[this.$L]
                                      }, l.locale = function(t, e) {
                                          if (!t)
                                              return this.$L;
                                          var n = this.clone(),
                                              r = Y(t, e, !0);
                                          return r && (n.$L = r), n
                                      }, l.clone = function() {
                                          return p.w(this.$d, this)
                                      }, l.toDate = function() {
                                          return new Date(this.valueOf())
                                      }, l.toJSON = function() {
                                          return this.isValid() ? this.toISOString() : null
                                      }, l.toISOString = function() {
                                          return this.$d.toISOString()
                                      }, l.toString = function() {
                                          return this.$d.toUTCString()
                                      }, d
                                  }(),
                                  g = y.prototype;
                              return v.prototype = g, [["$ms", t], ["$s", e], ["$m", n], ["$H", r], ["$W", i], ["$M", a], ["$y", u], ["$D", f]].forEach((function(t) {
                                  g[t[1]] = function(e) {
                                      return this.$g(e, t[0], t[1])
                                  }
                              })), v.extend = function(t, e) {
                                  return t.$i || (t(e, y, v), t.$i = !0), v
                              }, v.locale = Y, v.isDayjs = D, v.unix = function(t) {
                                  return v(1e3 * t)
                              }, v.en = m[$], v.Ls = m, v.p = {}, v
                          }()
                      })),
                      n = t((function(t, e) {
                          var n,
                              r,
                              i,
                              s,
                              a,
                              o,
                              u,
                              f,
                              h,
                              c,
                              d,
                              l,
                              M;
                          t.exports = (n = {
                              LTS: "h:mm:ss A",
                              LT: "h:mm A",
                              L: "MM/DD/YYYY",
                              LL: "MMMM D, YYYY",
                              LLL: "MMMM D, YYYY h:mm A",
                              LLLL: "dddd, MMMM D, YYYY h:mm A"
                          }, r = function(t, e) {
                              return t.replace(/(\[[^\]]+])|(LTS?|l{1,4}|L{1,4})/g, (function(t, r, i) {
                                  var s = i && i.toUpperCase();
                                  return r || e[i] || n[i] || e[s].replace(/(\[[^\]]+])|(MMMM|MM|DD|dddd)/g, (function(t, e, n) {
                                          return e || n.slice(1)
                                      }))
                              }))
                          }, i = /(\[[^[]*\])|([-:/.()\s]+)|(A|a|YYYY|YY?|MM?M?M?|Do|DD?|hh?|HH?|mm?|ss?|S{1,3}|z|ZZ?)/g, u = {}, h = [/[+-]\d\d:?(\d\d)?/, function(t) {
                              (this.zone || (this.zone = {})).offset = function(t) {
                                  if (!t)
                                      return 0;
                                  var e = t.match(/([+-]|\d\d)/g),
                                      n = 60 * e[1] + (+e[2] || 0);
                                  return 0 === n ? 0 : "+" === e[0] ? -n : n
                              }(t)
                          }], c = function(t) {
                              var e = u[t];
                              return e && (e.indexOf ? e : e.s.concat(e.f))
                          }, d = function(t, e) {
                              var n,
                                  r = u.meridiem;
                              if (r) {
                                  for (var i = 1; i <= 24; i += 1)
                                      if (t.indexOf(r(i, 0, e)) > -1) {
                                          n = i > 12;
                                          break
                                      }
                              } else
                                  n = t === (e ? "pm" : "PM");
                              return n
                          }, l = {
                              A: [o = /\d*[^\s\d-:/()]+/, function(t) {
                                  this.afternoon = d(t, !1)
                              }],
                              a: [o, function(t) {
                                  this.afternoon = d(t, !0)
                              }],
                              S: [/\d/, function(t) {
                                  this.milliseconds = 100 * +t
                              }],
                              SS: [s = /\d\d/, function(t) {
                                  this.milliseconds = 10 * +t
                              }],
                              SSS: [/\d{3}/, function(t) {
                                  this.milliseconds = +t
                              }],
                              s: [a = /\d\d?/, (f = function(t) {
                                  return function(e) {
                                      this[t] = +e
                                  }
                              })("seconds")],
                              ss: [a, f("seconds")],
                              m: [a, f("minutes")],
                              mm: [a, f("minutes")],
                              H: [a, f("hours")],
                              h: [a, f("hours")],
                              HH: [a, f("hours")],
                              hh: [a, f("hours")],
                              D: [a, f("day")],
                              DD: [s, f("day")],
                              Do: [o, function(t) {
                                  var e = u.ordinal,
                                      n = t.match(/\d+/);
                                  if (this.day = n[0], e)
                                      for (var r = 1; r <= 31; r += 1)
                                          e(r).replace(/\[|\]/g, "") === t && (this.day = r)
                              }],
                              M: [a, f("month")],
                              MM: [s, f("month")],
                              MMM: [o, function(t) {
                                  var e = c("months"),
                                      n = (c("monthsShort") || e.map((function(t) {
                                          return t.substr(0, 3)
                                      }))).indexOf(t) + 1;
                                  if (n < 1)
                                      throw new Error;
                                  this.month = n % 12 || n
                              }],
                              MMMM: [o, function(t) {
                                  var e = c("months").indexOf(t) + 1;
                                  if (e < 1)
                                      throw new Error;
                                  this.month = e % 12 || e
                              }],
                              Y: [/[+-]?\d+/, f("year")],
                              YY: [s, function(t) {
                                  t = +t,
                                  this.year = t + (t > 68 ? 1900 : 2e3)
                              }],
                              YYYY: [/\d{4}/, f("year")],
                              Z: h,
                              ZZ: h
                          }, M = function(t, e, n) {
                              try {
                                  var s = function(t) {
                                          for (var e = (t = r(t, u && u.formats)).match(i), n = e.length, s = 0; s < n; s += 1) {
                                              var a = e[s],
                                                  o = l[a],
                                                  f = o && o[0],
                                                  h = o && o[1];
                                              e[s] = h ? {
                                                  regex: f,
                                                  parser: h
                                              } : a.replace(/^\[|\]$/g, "")
                                          }
                                          return function(t) {
                                              for (var r = {}, i = 0, s = 0; i < n; i += 1) {
                                                  var a = e[i];
                                                  if ("string" == typeof a)
                                                      s += a.length;
                                                  else {
                                                      var o = a.regex,
                                                          u = a.parser,
                                                          f = t.substr(s),
                                                          h = o.exec(f)[0];
                                                      u.call(r, h),
                                                      t = t.replace(h, "")
                                                  }
                                              }
                                              return function(t) {
                                                  var e = t.afternoon;
                                                  if (void 0 !== e) {
                                                      var n = t.hours;
                                                      e ? n < 12 && (t.hours += 12) : 12 === n && (t.hours = 0),
                                                      delete t.afternoon
                                                  }
                                              }(r), r
                                          }
                                      }(e)(t),
                                      a = s.year,
                                      o = s.month,
                                      f = s.day,
                                      h = s.hours,
                                      c = s.minutes,
                                      d = s.seconds,
                                      M = s.milliseconds,
                                      $ = s.zone,
                                      m = new Date,
                                      D = f || (a || o ? 1 : m.getDate()),
                                      Y = a || m.getFullYear(),
                                      v = 0;
                                  a && !o || (v = o > 0 ? o - 1 : m.getMonth());
                                  var p = h || 0,
                                      y = c || 0,
                                      g = d || 0,
                                      S = M || 0;
                                  return $ ? new Date(Date.UTC(Y, v, D, p, y, g, S + 60 * $.offset * 1e3)) : n ? new Date(Date.UTC(Y, v, D, p, y, g, S)) : new Date(Y, v, D, p, y, g, S)
                              } catch (t) {
                                  return new Date("")
                              }
                          }, function(t, e, n) {
                              n.p.customParseFormat = !0;
                              var r = e.prototype,
                                  i = r.parse;
                              r.parse = function(t) {
                                  var e = t.date,
                                      r = t.utc,
                                      s = t.args;
                                  this.$u = r;
                                  var a = s[1];
                                  if ("string" == typeof a) {
                                      var o = !0 === s[2],
                                          f = !0 === s[3],
                                          h = o || f,
                                          c = s[2];
                                      f && (c = s[2]),
                                      u = this.$locale(),
                                      !o && c && (u = n.Ls[c]),
                                      this.$d = M(e, a, r),
                                      this.init(),
                                      c && !0 !== c && (this.$L = this.locale(c).$L),
                                      h && e !== this.format(a) && (this.$d = new Date("")),
                                      u = {}
                                  } else if (a instanceof Array)
                                      for (var d = a.length, l = 1; l <= d; l += 1) {
                                          s[1] = a[l - 1];
                                          var $ = n.apply(this, s);
                                          if ($.isValid()) {
                                              this.$d = $.$d,
                                              this.$L = $.$L,
                                              this.init();
                                              break
                                          }
                                          l === d && (this.$d = new Date(""))
                                      }
                                  else
                                      i.call(this, t)
                              }
                          })
                      }));
                  e.extend(n);
                  exports.parseDate = (t, n) => {
                      let r = !1;
                      if (n)
                          switch (n) {
                          case "ISO_8601":
                              r = t;
                              break;
                          case "RFC_2822":
                              r = e(t, "ddd, MM MMM YYYY HH:mm:ss ZZ").format("YYYYMMDD");
                              break;
                          case "MYSQL":
                              r = e(t, "YYYY-MM-DD hh:mm:ss").format("YYYYMMDD");
                              break;
                          case "UNIX":
                              r = e(t).unix();
                              break;
                          default:
                              r = e(t, n).format("YYYYMMDD")
                          }
                      return r
                  };


              }).call(this)
          }).call(this, typeof global !== "undefined" ? global : typeof self !== "undefined" ? self : typeof window !== "undefined" ? window : {})
      }, {}],
      2: [function(require, module, exports) {
          "use strict";
          Object.defineProperty(exports, "__esModule", {
              value: !0
          });
          const t = t => "[object Object]" === Object.prototype.toString.call(t),
              e = (t, e) => {
                  const s = document.createElement(t);
                  if (e && "object" == typeof e)
                      for (const t in e)
                          "html" === t ? s.innerHTML = e[t] : s.setAttribute(t, e[t]);
                  return s
              },
              s = t => {
                  t instanceof NodeList ? t.forEach((t => s(t))) : t.innerHTML = ""
              },
              a = (t, s, a) => e("li", {
                  class: t,
                  html: `<a href="#" data-page="${s}">${a}</a>`
              }),
              i = (t, e) => {
                  let s,
                      a;
                  1 === e ? (s = 0, a = t.length) : -1 === e && (s = t.length - 1, a = -1);
                  for (let i = !0; i;) {
                      i = !1;
                      for (let n = s; n != a; n += e)
                          if (t[n + e] && t[n].value > t[n + e].value) {
                              const s = t[n],
                                  a = t[n + e],
                                  h = s;
                              t[n] = a,
                              t[n + e] = h,
                              i = !0
                          }
                  }
                  return t
              };
          class n {
              constructor(t, e)
              {
                  return this.dt = t, this.rows = e, this
              }
              build(t)
              {
                  const s = e("tr");
                  let a = this.dt.headings;
                  return a.length || (a = t.map((() => ""))), a.forEach(((a, i) => {
                      const n = e("td");
                      t[i] && t[i].length || (t[i] = ""),
                      n.innerHTML = t[i],
                      n.data = t[i],
                      s.appendChild(n)
                  })), s
              }
              render(t)
              {
                  return t
              }
              add(t)
              {
                  if (Array.isArray(t)) {
                      const e = this.dt;
                      Array.isArray(t[0]) ? t.forEach((t => {
                          e.data.push(this.build(t))
                      })) : e.data.push(this.build(t)),
                      e.data.length && (e.hasRows = !0),
                      this.update(),
                      e.columns().rebuild()
                  }
              }
              remove(t)
              {
                  const e = this.dt;
                  Array.isArray(t) ? (t.sort(((t, e) => e - t)), t.forEach((t => {
                      e.data.splice(t, 1)
                  }))) : "all" == t ? e.data = [] : e.data.splice(t, 1),
                  e.data.length || (e.hasRows = !1),
                  this.update(),
                  e.columns().rebuild()
              }
              update()
              {
                  this.dt.data.forEach(((t, e) => {
                      t.dataIndex = e
                  }))
              }
          }
          class h {
              constructor(t)
              {
                  return this.dt = t, this
              }
              swap(t)
              {
                  if (t.length && 2 === t.length) {
                      const e = [];
                      this.dt.headings.forEach(((t, s) => {
                          e.push(s)
                      }));
                      const s = t[0],
                          a = t[1],
                          i = e[a];
                      e[a] = e[s],
                      e[s] = i,
                      this.order(e)
                  }
              }
              order(t)
              {
                  let e,
                      s,
                      a,
                      i,
                      n,
                      h,
                      l;
                  const r = [[], [], [], []],
                      o = this.dt;
                  t.forEach(((t, a) => {
                      n = o.headings[t],
                      h = "false" !== n.getAttribute("data-sortable"),
                      e = n.cloneNode(!0),
                      e.originalCellIndex = a,
                      e.sortable = h,
                      r[0].push(e),
                      o.hiddenColumns.includes(t) || (s = n.cloneNode(!0), s.originalCellIndex = a, s.sortable = h, r[1].push(s))
                  })),
                  o.data.forEach(((e, s) => {
                      a = e.cloneNode(!1),
                      i = e.cloneNode(!1),
                      a.dataIndex = i.dataIndex = s,
                      null !== e.searchIndex && void 0 !== e.searchIndex && (a.searchIndex = i.searchIndex = e.searchIndex),
                      t.forEach((t => {
                          l = e.cells[t].cloneNode(!0),
                          l.data = e.cells[t].data,
                          a.appendChild(l),
                          o.hiddenColumns.includes(t) || (l = e.cells[t].cloneNode(!0), l.data = e.cells[t].data, i.appendChild(l))
                      })),
                      r[2].push(a),
                      r[3].push(i)
                  })),
                  o.headings = r[0],
                  o.activeHeadings = r[1],
                  o.data = r[2],
                  o.activeRows = r[3],
                  o.update()
              }
              hide(t)
              {
                  if (t.length) {
                      const e = this.dt;
                      t.forEach((t => {
                          e.hiddenColumns.includes(t) || e.hiddenColumns.push(t)
                      })),
                      this.rebuild()
                  }
              }
              show(t)
              {
                  if (t.length) {
                      let e;
                      const s = this.dt;
                      t.forEach((t => {
                          e = s.hiddenColumns.indexOf(t),
                          e > -1 && s.hiddenColumns.splice(e, 1)
                      })),
                      this.rebuild()
                  }
              }
              visible(t)
              {
                  let e;
                  const s = this.dt;
                  return t = t || s.headings.map((t => t.originalCellIndex)), isNaN(t) ? Array.isArray(t) && (e = [], t.forEach((t => {
                      e.push(!s.hiddenColumns.includes(t))
                  }))) : e = !s.hiddenColumns.includes(t), e
              }
              add(t)
              {
                  let e;
                  const s = document.createElement("th");
                  if (!this.dt.headings.length)
                      return this.dt.insert({
                          headings: [t.heading],
                          data: t.data.map((t => [t]))
                      }), void this.rebuild();
                  this.dt.hiddenHeader ? s.innerHTML = "" : t.heading.nodeName ? s.appendChild(t.heading) : s.innerHTML = t.heading,
                  this.dt.headings.push(s),
                  this.dt.data.forEach(((s, a) => {
                      t.data[a] && (e = document.createElement("td"), t.data[a].nodeName ? e.appendChild(t.data[a]) : e.innerHTML = t.data[a], e.data = e.innerHTML, t.render && (e.innerHTML = t.render.call(this, e.data, e, s)), s.appendChild(e))
                  })),
                  t.type && s.setAttribute("data-type", t.type),
                  t.format && s.setAttribute("data-format", t.format),
                  t.hasOwnProperty("sortable") && (s.sortable = t.sortable, s.setAttribute("data-sortable", !0 === t.sortable ? "true" : "false")),
                  this.rebuild(),
                  this.dt.renderHeader()
              }
              remove(t)
              {
                  Array.isArray(t) ? (t.sort(((t, e) => e - t)), t.forEach((t => this.remove(t)))) : (this.dt.headings.splice(t, 1), this.dt.data.forEach((e => {
                      e.removeChild(e.cells[t])
                  }))),
                  this.rebuild()
              }
              filter(t, e, s, a)
              {
                  const i = this.dt;
                  if (i.filterState || (i.filterState = {
                      originalData: i.data
                  }), !i.filterState[t]) {
                      const e = [...a, () => !0];
                      i.filterState[t] = function() {
                          let t = 0;
                          return () => e[t++ % e.length]
                      }()
                  }
                  const n = i.filterState[t](),
                      h = Array.from(i.filterState.originalData).filter((e => {
                          const s = e.cells[t],
                              a = s.hasAttribute("data-content") ? s.getAttribute("data-content") : s.innerText;
                          return "function" == typeof n ? n(a) : a === n
                      }));
                  i.data = h,
                  this.rebuild(),
                  i.update(),
                  s || i.emit("datatable.sort", t, e)
              }
              sort(t, e, s)
              {
                  const a = this.dt;
                  if (a.hasHeadings && (t < 0 || t > a.headings.length))
                      return !1;
                  const n = a.options.filters && a.options.filters[a.headings[t].textContent];
                  if (n && 0 !== n.length)
                      return void this.filter(t, e, s, n);
                  a.sorting = !0,
                  s || a.emit("datatable.sorting", t, e);
                  let h = a.data;
                  const l = [],
                      r = [];
                  let o = 0,
                      d = 0;
                  const c = a.headings[t],
                      p = [];
                  if ("date" === c.getAttribute("data-type")) {
                      let t = !1;
                      c.hasAttribute("data-format") && (t = c.getAttribute("data-format")),
                      p.push(Promise.resolve().then((function() {
                          return require("./date-cd1c23ce.js")
                      })).then((({parseDate: e}) => s => e(s, t))))
                  }
                  Promise.all(p).then((n => {
                      const p = n[0];
                      let g,
                          u;
                      Array.from(h).forEach((e => {
                          const s = e.cells[t],
                              a = s.hasAttribute("data-content") ? s.getAttribute("data-content") : s.innerText;
                          let i;
                          i = p ? p(a) : "string" == typeof a ? a.replace(/(\$|,|\s|%)/g, "") : a,
                          parseFloat(i) == i ? r[d++] = {
                              value: Number(i),
                              row: e
                          } : l[o++] = {
                              value: "string" == typeof a ? a.toLowerCase() : a,
                              row: e
                          }
                      })),
                      e || (e = c.classList.contains("asc") ? "desc" : "asc"),
                      "desc" == e ? (g = i(l, -1), u = i(r, -1), c.classList.remove("asc"), c.classList.add("desc")) : (g = i(r, 1), u = i(l, 1), c.classList.remove("desc"), c.classList.add("asc")),
                      a.lastTh && c != a.lastTh && (a.lastTh.classList.remove("desc"), a.lastTh.classList.remove("asc")),
                      a.lastTh = c,
                      h = g.concat(u),
                      a.data = [];
                      const f = [];
                      h.forEach(((t, e) => {
                          a.data.push(t.row),
                          null !== t.row.searchIndex && void 0 !== t.row.searchIndex && f.push(e)
                      })),
                      a.searchData = f,
                      this.rebuild(),
                      a.update(),
                      s || a.emit("datatable.sort", t, e)
                  }))
              }
              rebuild()
              {
                  let t,
                      e,
                      s,
                      a;
                  const i = this.dt,
                      n = [];
                  i.activeRows = [],
                  i.activeHeadings = [],
                  i.headings.forEach(((t, e) => {
                      t.originalCellIndex = e,
                      t.sortable = "false" !== t.getAttribute("data-sortable"),
                      i.hiddenColumns.includes(e) || i.activeHeadings.push(t)
                  })),
                  i.data.forEach(((h, l) => {
                      t = h.cloneNode(!1),
                      e = h.cloneNode(!1),
                      t.dataIndex = e.dataIndex = l,
                      null !== h.searchIndex && void 0 !== h.searchIndex && (t.searchIndex = e.searchIndex = h.searchIndex),
                      Array.from(h.cells).forEach((n => {
                          s = n.cloneNode(!0),
                          s.data = n.data,
                          t.appendChild(s),
                          i.hiddenColumns.includes(s.cellIndex) || (a = s.cloneNode(!0), a.data = s.data, e.appendChild(a))
                      })),
                      n.push(t),
                      i.activeRows.push(e)
                  })),
                  i.data = n,
                  i.update()
              }
          }
          const l = function(t) {
                  let s = !1,
                      a = !1;
                  if ((t = t || this.options.data).headings) {
                      s = e("thead");
                      const a = e("tr");
                      t.headings.forEach((t => {
                          const s = e("th", {
                              html: t
                          });
                          a.appendChild(s)
                      })),
                      s.appendChild(a)
                  }
                  t.data && t.data.length && (a = e("tbody"), t.data.forEach((s => {
                      if (t.headings && t.headings.length !== s.length)
                          throw new Error("The number of rows do not match the number of headings.");
                      const i = e("tr");
                      s.forEach((t => {
                          const s = e("td", {
                              html: t
                          });
                          i.appendChild(s)
                      })),
                      a.appendChild(i)
                  }))),
                  s && (null !== this.table.tHead && this.table.removeChild(this.table.tHead), this.table.appendChild(s)),
                  a && (this.table.tBodies.length && this.table.removeChild(this.table.tBodies[0]), this.table.appendChild(a))
              },
              r = {
                  sortable: !0,
                  searchable: !0,
                  paging: !0,
                  perPage: 10,
                  perPageSelect: [5, 10, 15, 20, 25],
                  nextPrev: !0,
                  firstLast: !1,
                  prevText: "&lsaquo;",
                  nextText: "&rsaquo;",
                  firstText: "&laquo;",
                  lastText: "&raquo;",
                  ellipsisText: "&hellip;",
                  ascText: "▴",
                  descText: "▾",
                  truncatePager: !0,
                  pagerDelta: 2,
                  scrollY: "",
                  fixedColumns: !0,
                  fixedHeight: !1,
                  header: !0,
                  hiddenHeader: !1,
                  footer: !1,
                  labels: {
                      placeholder: "Search...",
                      perPage: "{select} entries per page",
                      noRows: "No entries found",
                      info: "Showing {start} to {end} of {rows} entries"
                  },
                  layout: {
                      top: "{select}{search}",
                      bottom: "{info}{pager}"
                  }
              };
          class o {
              constructor(t, e={})
              {
                  if (this.initialized = !1, this.options = {
                      ...r,
                      ...e,
                      layout: {
                          ...r.layout,
                          ...e.layout
                      },
                      labels: {
                          ...r.labels,
                          ...e.labels
                      }
                  }, "string" == typeof t && (t = document.querySelector(t)), this.initialLayout = t.innerHTML, this.initialSortable = this.options.sortable, this.options.header || (this.options.sortable = !1), null === t.tHead && (!this.options.data || this.options.data && !this.options.data.headings) && (this.options.sortable = !1), t.tBodies.length && !t.tBodies[0].rows.length && this.options.data && !this.options.data.data)
                      throw new Error("You seem to be using the data option, but you've not defined any rows.");
                  this.table = t,
                  this.listeners = {
                      onResize: t => this.onResize(t)
                  },
                  this.init()
              }
              static extend(t, e)
              {
                  "function" == typeof e ? o.prototype[t] = e : o[t] = e
              }
              init(t)
              {
                  if (this.initialized || this.table.classList.contains("dataTable-table"))
                      return !1;
                  Object.assign(this.options, t || {}),
                  this.currentPage = 1,
                  this.onFirstPage = !0,
                  this.hiddenColumns = [],
                  this.columnRenderers = [],
                  this.selectedColumns = [],
                  this.render(),
                  setTimeout((() => {
                      this.emit("datatable.init"),
                      this.initialized = !0,
                      this.options.plugins && Object.entries(this.options.plugins).forEach((([t, s]) => {
                          this[t] && "function" == typeof this[t] && (this[t] = this[t](s, {
                              createElement: e
                          }), s.enabled && this[t].init && "function" == typeof this[t].init && this[t].init())
                      }))
                  }), 10)
              }
              render(t)
              {
                  if (t) {
                      switch (t) {
                      case "page":
                          this.renderPage();
                          break;
                      case "pager":
                          this.renderPager();
                          break;
                      case "header":
                          this.renderHeader()
                      }
                      return !1
                  }
                  const s = this.options;
                  let a = "";
                  if (s.data && l.call(this), this.body = this.table.tBodies[0], this.head = this.table.tHead, this.foot = this.table.tFoot, this.body || (this.body = e("tbody"), this.table.appendChild(this.body)), this.hasRows = this.body.rows.length > 0, !this.head) {
                      const t = e("thead"),
                          a = e("tr");
                      this.hasRows && (Array.from(this.body.rows[0].cells).forEach((() => {
                          a.appendChild(e("th"))
                      })), t.appendChild(a)),
                      this.head = t,
                      this.table.insertBefore(this.head, this.body),
                      this.hiddenHeader = s.hiddenHeader
                  }
                  if (this.headings = [], this.hasHeadings = this.head.rows.length > 0, this.hasHeadings && (this.header = this.head.rows[0], this.headings = [].slice.call(this.header.cells)), s.header || this.head && this.table.removeChild(this.table.tHead), s.footer ? this.head && !this.foot && (this.foot = e("tfoot", {
                      html: this.head.innerHTML
                  }), this.table.appendChild(this.foot)) : this.foot && this.table.removeChild(this.table.tFoot), this.wrapper = e("div", {
                      class: "dataTable-wrapper dataTable-loading"
                  }), a += "<div class='dataTable-top'>", a += s.layout.top, a += "</div>", s.scrollY.length ? a += `<div class='dataTable-container' style='height: ${s.scrollY}; overflow-Y: auto;'></div>` : a += "<div class='dataTable-container'></div>", a += "<div class='dataTable-bottom'>", a += s.layout.bottom, a += "</div>", a = a.replace("{info}", s.paging ? "<div class='dataTable-info'></div>" : ""), s.paging && s.perPageSelect) {
                      let t = "<div class='dataTable-dropdown'><label>";
                      t += s.labels.perPage,
                      t += "</label></div>";
                      const i = e("select", {
                          class: "dataTable-selector"
                      });
                      s.perPageSelect.forEach((t => {
                          const e = t === s.perPage,
                              a = new Option(t, t, e, e);
                          i.add(a)
                      })),
                      t = t.replace("{select}", i.outerHTML),
                      a = a.replace("{select}", t)
                  } else
                      a = a.replace("{select}", "");
                  if (s.searchable) {
                      const t = `<div class='dataTable-search'><input class='dataTable-input' placeholder='${s.labels.placeholder}' type='text'></div>`;
                      a = a.replace("{search}", t)
                  } else
                      a = a.replace("{search}", "");
                  this.hasHeadings && this.render("header"),
                  this.table.classList.add("dataTable-table");
                  const i = e("nav", {
                          class: "dataTable-pagination"
                      }),
                      n = e("ul", {
                          class: "dataTable-pagination-list"
                      });
                  i.appendChild(n),
                  a = a.replace(/\{pager\}/g, i.outerHTML),
                  this.wrapper.innerHTML = a,
                  this.container = this.wrapper.querySelector(".dataTable-container"),
                  this.pagers = this.wrapper.querySelectorAll(".dataTable-pagination-list"),
                  this.label = this.wrapper.querySelector(".dataTable-info"),
                  this.table.parentNode.replaceChild(this.wrapper, this.table),
                  this.container.appendChild(this.table),
                  this.rect = this.table.getBoundingClientRect(),
                  this.data = Array.from(this.body.rows),
                  this.activeRows = this.data.slice(),
                  this.activeHeadings = this.headings.slice(),
                  this.update(),
                  this.setColumns(),
                  this.fixHeight(),
                  this.fixColumns(),
                  s.header || this.wrapper.classList.add("no-header"),
                  s.footer || this.wrapper.classList.add("no-footer"),
                  s.sortable && this.wrapper.classList.add("sortable"),
                  s.searchable && this.wrapper.classList.add("searchable"),
                  s.fixedHeight && this.wrapper.classList.add("fixed-height"),
                  s.fixedColumns && this.wrapper.classList.add("fixed-columns"),
                  this.bindEvents()
              }
              renderPage()
              {
                  if (this.hasHeadings && (s(this.header), this.activeHeadings.forEach((t => this.header.appendChild(t)))), this.hasRows && this.totalPages) {
                      this.currentPage > this.totalPages && (this.currentPage = 1);
                      const t = this.currentPage - 1,
                          e = document.createDocumentFragment();
                      this.pages[t].forEach((t => e.appendChild(this.rows().render(t)))),
                      this.clear(e),
                      this.onFirstPage = 1 === this.currentPage,
                      this.onLastPage = this.currentPage === this.lastPage
                  } else
                      this.setMessage(this.options.labels.noRows);
                  let t,
                      e = 0,
                      a = 0,
                      i = 0;
                  if (this.totalPages && (e = this.currentPage - 1, a = e * this.options.perPage, i = a + this.pages[e].length, a += 1, t = this.searching ? this.searchData.length : this.data.length), this.label && this.options.labels.info.length) {
                      const e = this.options.labels.info.replace("{start}", a).replace("{end}", i).replace("{page}", this.currentPage).replace("{pages}", this.totalPages).replace("{rows}", t);
                      this.label.innerHTML = t ? e : ""
                  }
                  1 == this.currentPage && this.fixHeight()
              }
              renderPager()
              {
                  if (s(this.pagers), this.totalPages > 1) {
                      const t = "pager",
                          s = document.createDocumentFragment(),
                          i = this.onFirstPage ? 1 : this.currentPage - 1,
                          n = this.onLastPage ? this.totalPages : this.currentPage + 1;
                      this.options.firstLast && s.appendChild(a(t, 1, this.options.firstText)),
                      this.options.nextPrev && s.appendChild(a(t, i, this.options.prevText));
                      let h = this.links;
                      this.options.truncatePager && (h = ((t, s, a, i, n) => {
                          let h;
                          const l = 2 * (i = i || 2);
                          let r = s - i,
                              o = s + i;
                          const d = [],
                              c = [];
                          s < 4 - i + l ? o = 3 + l : s > a - (3 - i + l) && (r = a - (2 + l));
                          for (let e = 1; e <= a; e++)
                              if (1 == e || e == a || e >= r && e <= o) {
                                  const s = t[e - 1];
                                  s.classList.remove("active"),
                                  d.push(s)
                              }
                          return d.forEach((s => {
                              const a = s.children[0].getAttribute("data-page");
                              if (h) {
                                  const s = h.children[0].getAttribute("data-page");
                                  if (a - s == 2)
                                      c.push(t[s]);
                                  else if (a - s != 1) {
                                      const t = e("li", {
                                          class: "ellipsis",
                                          html: `<a href="#">${n}</a>`
                                      });
                                      c.push(t)
                                  }
                              }
                              c.push(s),
                              h = s
                          })), c
                      })(this.links, this.currentPage, this.pages.length, this.options.pagerDelta, this.options.ellipsisText)),
                      this.links[this.currentPage - 1].classList.add("active"),
                      h.forEach((t => {
                          t.classList.remove("active"),
                          s.appendChild(t)
                      })),
                      this.links[this.currentPage - 1].classList.add("active"),
                      this.options.nextPrev && s.appendChild(a(t, n, this.options.nextText)),
                      this.options.firstLast && s.appendChild(a(t, this.totalPages, this.options.lastText)),
                      this.pagers.forEach((t => {
                          t.appendChild(s.cloneNode(!0))
                      }))
                  }
              }
              renderHeader()
              {
                  this.labels = [],
                  this.headings && this.headings.length && this.headings.forEach(((t, s) => {
                      if (this.labels[s] = t.textContent, t.firstElementChild && t.firstElementChild.classList.contains("dataTable-sorter") && (t.innerHTML = t.firstElementChild.innerHTML), t.sortable = "false" !== t.getAttribute("data-sortable"), t.originalCellIndex = s, this.options.sortable && t.sortable) {
                          const s = e("a", {
                              href: "#",
                              class: "dataTable-sorter",
                              html: t.innerHTML
                          });
                          t.innerHTML = "",
                          t.setAttribute("data-sortable", ""),
                          t.appendChild(s)
                      }
                  })),
                  this.fixColumns()
              }
              bindEvents()
              {
                  const t = this.options;
                  if (t.perPageSelect) {
                      const e = this.wrapper.querySelector(".dataTable-selector");
                      e && e.addEventListener("change", (() => {
                          t.perPage = parseInt(e.value, 10),
                          this.update(),
                          this.fixHeight(),
                          this.emit("datatable.perpage", t.perPage)
                      }), !1)
                  }
                  t.searchable && (this.input = this.wrapper.querySelector(".dataTable-input"), this.input && this.input.addEventListener("keyup", (() => this.search(this.input.value)), !1)),
                  this.wrapper.addEventListener("click", (e => {
                      const s = e.target.closest("a");
                      s && "a" === s.nodeName.toLowerCase() && (s.hasAttribute("data-page") ? (this.page(s.getAttribute("data-page")), e.preventDefault()) : t.sortable && s.classList.contains("dataTable-sorter") && "false" != s.parentNode.getAttribute("data-sortable") && (this.columns().sort(this.headings.indexOf(s.parentNode)), e.preventDefault()))
                  }), !1),
                  window.addEventListener("resize", this.listeners.onResize)
              }
              onResize()
              {
                  this.rect = this.container.getBoundingClientRect(),
                  this.rect.width && this.fixColumns()
              }
              setColumns(t)
              {
                  t || this.data.forEach((t => {
                      Array.from(t.cells).forEach((t => {
                          t.data = t.innerHTML
                      }))
                  })),
                  this.options.columns && this.headings.length && this.options.columns.forEach((t => {
                      Array.isArray(t.select) || (t.select = [t.select]),
                      t.hasOwnProperty("render") && "function" == typeof t.render && (this.selectedColumns = this.selectedColumns.concat(t.select), this.columnRenderers.push({
                          columns: t.select,
                          renderer: t.render
                      })),
                      t.select.forEach((e => {
                          const s = this.headings[e];
                          t.type && s.setAttribute("data-type", t.type),
                          t.format && s.setAttribute("data-format", t.format),
                          t.hasOwnProperty("sortable") && s.setAttribute("data-sortable", t.sortable),
                          t.hasOwnProperty("hidden") && !1 !== t.hidden && this.columns().hide([e]),
                          t.hasOwnProperty("sort") && 1 === t.select.length && this.columns().sort(t.select[0], t.sort, !0)
                      }))
                  })),
                  this.hasRows && (this.data.forEach(((t, e) => {
                      t.dataIndex = e,
                      Array.from(t.cells).forEach((t => {
                          t.data = t.innerHTML
                      }))
                  })), this.selectedColumns.length && this.data.forEach((t => {
                      Array.from(t.cells).forEach(((e, s) => {
                          this.selectedColumns.includes(s) && this.columnRenderers.forEach((a => {
                              a.columns.includes(s) && (e.innerHTML = a.renderer.call(this, e.data, e, t))
                          }))
                      }))
                  })), this.columns().rebuild()),
                  this.render("header")
              }
              destroy()
              {
                  this.table.innerHTML = this.initialLayout,
                  this.table.classList.remove("dataTable-table"),
                  this.wrapper.parentNode.replaceChild(this.table, this.wrapper),
                  this.initialized = !1,
                  window.removeEventListener("resize", this.listeners.onResize)
              }
              update()
              {
                  this.wrapper.classList.remove("dataTable-empty"),
                  this.paginate(this),
                  this.render("page"),
                  this.links = [];
                  let t = this.pages.length;
                  for (; t--;) {
                      const e = t + 1;
                      this.links[t] = a(0 === t ? "active" : "", e, e)
                  }
                  this.sorting = !1,
                  this.render("pager"),
                  this.rows().update(),
                  this.emit("datatable.update")
              }
              paginate()
              {
                  const t = this.options.perPage;
                  let e = this.activeRows;
                  return this.searching && (e = [], this.searchData.forEach((t => e.push(this.activeRows[t])))), this.options.paging ? this.pages = e.map(((s, a) => a % t == 0 ? e.slice(a, a + t) : null)).filter((t => t)) : this.pages = [e], this.totalPages = this.lastPage = this.pages.length, this.totalPages
              }
              fixColumns()
              {
                  if ((this.options.scrollY.length || this.options.fixedColumns) && this.activeHeadings && this.activeHeadings.length) {
                      let t,
                          s = !1;
                      if (this.columnWidths = [], this.table.tHead) {
                          if (this.options.scrollY.length && (s = e("thead"), s.appendChild(e("tr")), s.style.height = "0px", this.headerTable && (this.table.tHead = this.headerTable.tHead)), this.activeHeadings.forEach((t => {
                              t.style.width = ""
                          })), this.activeHeadings.forEach(((t, a) => {
                              const i = t.offsetWidth,
                                  n = i / this.rect.width * 100;
                              if (t.style.width = `${n}%`, this.columnWidths[a] = i, this.options.scrollY.length) {
                                  const t = e("th");
                                  s.firstElementChild.appendChild(t),
                                  t.style.width = `${n}%`,
                                  t.style.paddingTop = "0",
                                  t.style.paddingBottom = "0",
                                  t.style.border = "0"
                              }
                          })), this.options.scrollY.length) {
                              const t = this.table.parentElement;
                              if (!this.headerTable) {
                                  this.headerTable = e("table", {
                                      class: "dataTable-table"
                                  });
                                  const s = e("div", {
                                      class: "dataTable-headercontainer"
                                  });
                                  s.appendChild(this.headerTable),
                                  t.parentElement.insertBefore(s, t)
                              }
                              const a = this.table.tHead;
                              this.table.replaceChild(s, a),
                              this.headerTable.tHead = a,
                              this.headerTable.parentElement.style.paddingRight = `${this.headerTable.clientWidth - this.table.clientWidth + parseInt(this.headerTable.parentElement.style.paddingRight || "0", 10)}px`,
                              t.scrollHeight > t.clientHeight && (t.style.overflowY = "scroll")
                          }
                      } else {
                          t = [],
                          s = e("thead");
                          const a = e("tr");
                          Array.from(this.table.tBodies[0].rows[0].cells).forEach((() => {
                              const s = e("th");
                              a.appendChild(s),
                              t.push(s)
                          })),
                          s.appendChild(a),
                          this.table.insertBefore(s, this.body);
                          const i = [];
                          t.forEach(((t, e) => {
                              const s = t.offsetWidth,
                                  a = s / this.rect.width * 100;
                              i.push(a),
                              this.columnWidths[e] = s
                          })),
                          this.data.forEach((t => {
                              Array.from(t.cells).forEach(((t, e) => {
                                  this.columns(t.cellIndex).visible() && (t.style.width = `${i[e]}%`)
                              }))
                          })),
                          this.table.removeChild(s)
                      }
                  }
              }
              fixHeight()
              {
                  this.options.fixedHeight && (this.container.style.height = null, this.rect = this.container.getBoundingClientRect(), this.container.style.height = `${this.rect.height}px`)
              }
              search(t)
              {
                  return !!this.hasRows && (t = t.toLowerCase(), this.currentPage = 1, this.searching = !0, this.searchData = [], t.length ? (this.clear(), this.data.forEach(((e, s) => {
                          const a = this.searchData.includes(e);
                          t.split(" ").reduce(((t, s) => {
                              let a = !1,
                                  i = null,
                                  n = null;
                              for (let t = 0; t < e.cells.length; t++)
                                  if (i = e.cells[t], n = i.hasAttribute("data-content") ? i.getAttribute("data-content") : i.textContent, n.toLowerCase().includes(s) && this.columns(i.cellIndex).visible()) {
                                      a = !0;
                                      break
                                  }
                              return t && a
                          }), !0) && !a ? (e.searchIndex = s, this.searchData.push(s)) : e.searchIndex = null
                      })), this.wrapper.classList.add("search-results"), this.searchData.length ? this.update() : (this.wrapper.classList.remove("search-results"), this.setMessage(this.options.labels.noRows)), void this.emit("datatable.search", t, this.searchData)) : (this.searching = !1, this.update(), this.emit("datatable.search", t, this.searchData), this.wrapper.classList.remove("search-results"), !1))
              }
              page(t)
              {
                  return t != this.currentPage && (isNaN(t) || (this.currentPage = parseInt(t, 10)), !(t > this.pages.length || t < 0) && (this.render("page"), this.render("pager"), void this.emit("datatable.page", t)))
              }
              sortColumn(t, e)
              {
                  this.columns().sort(t, e)
              }
              insert(s)
              {
                  let a = [];
                  if (t(s)) {
                      if (s.headings && !this.hasHeadings && !this.hasRows) {
                          const t = e("tr");
                          s.headings.forEach((s => {
                              const a = e("th", {
                                  html: s
                              });
                              t.appendChild(a)
                          })),
                          this.head.appendChild(t),
                          this.header = t,
                          this.headings = [].slice.call(t.cells),
                          this.hasHeadings = !0,
                          this.options.sortable = this.initialSortable,
                          this.render("header"),
                          this.activeHeadings = this.headings.slice()
                      }
                      s.data && Array.isArray(s.data) && (a = s.data)
                  } else
                      Array.isArray(s) && s.forEach((t => {
                          const e = [];
                          Object.entries(t).forEach((([t, s]) => {
                              const a = this.labels.indexOf(t);
                              a > -1 && (e[a] = s)
                          })),
                          a.push(e)
                      }));
                  a.length && (this.rows().add(a), this.hasRows = !0),
                  this.update(),
                  this.setColumns(),
                  this.fixColumns()
              }
              refresh()
              {
                  this.options.searchable && (this.input.value = "", this.searching = !1),
                  this.currentPage = 1,
                  this.onFirstPage = !0,
                  this.update(),
                  this.emit("datatable.refresh")
              }
              clear(t)
              {
                  this.body && s(this.body);
                  let e = this.body;
                  if (this.body || (e = this.table), t) {
                      if ("string" == typeof t) {
                          document.createDocumentFragment().innerHTML = t
                      }
                      e.appendChild(t)
                  }
              }
              export(e)
              {
                  if (!this.hasHeadings && !this.hasRows)
                      return !1;
                  const s = this.activeHeadings;
                  let a = [];
                  const i = [];
                  let n,
                      h,
                      l,
                      r;
                  if (!t(e))
                      return !1;
                  const o = {
                      download: !0,
                      skipColumn: [],
                      lineDelimiter: "\n",
                      columnDelimiter: ",",
                      tableName: "myTable",
                      replacer: null,
                      space: 4,
                      ...e
                  };
                  if (o.type) {
                      if ("txt" !== o.type && "csv" !== o.type || (a[0] = this.header), o.selection)
                          if (isNaN(o.selection)) {
                              if (Array.isArray(o.selection))
                                  for (n = 0; n < o.selection.length; n++)
                                      a = a.concat(this.pages[o.selection[n] - 1])
                          } else
                              a = a.concat(this.pages[o.selection - 1]);
                      else
                          a = a.concat(this.activeRows);
                      if (a.length) {
                          if ("txt" === o.type || "csv" === o.type) {
                              for (l = "", n = 0; n < a.length; n++) {
                                  for (h = 0; h < a[n].cells.length; h++)
                                      if (!o.skipColumn.includes(s[h].originalCellIndex) && this.columns(s[h].originalCellIndex).visible()) {
                                          let t = a[n].cells[h].textContent;
                                          t = t.trim(),
                                          t = t.replace(/\s{2,}/g, " "),
                                          t = t.replace(/\n/g, "  "),
                                          t = t.replace(/"/g, '""'),
                                          t = t.replace(/#/g, "%23"),
                                          t.includes(",") && (t = `"${t}"`),
                                          l += t + o.columnDelimiter
                                      }
                                  l = l.trim().substring(0, l.length - 1),
                                  l += o.lineDelimiter
                              }
                              l = l.trim().substring(0, l.length - 1),
                              o.download && (l = `data:text/csv;charset=utf-8,${l}`)
                          } else if ("sql" === o.type) {
                              for (l = `INSERT INTO \`${o.tableName}\` (`, n = 0; n < s.length; n++)
                                  !o.skipColumn.includes(s[n].originalCellIndex) && this.columns(s[n].originalCellIndex).visible() && (l += `\`${s[n].textContent}\`,`);
                              for (l = l.trim().substring(0, l.length - 1), l += ") VALUES ", n = 0; n < a.length; n++) {
                                  for (l += "(", h = 0; h < a[n].cells.length; h++)
                                      !o.skipColumn.includes(s[h].originalCellIndex) && this.columns(s[h].originalCellIndex).visible() && (l += `"${a[n].cells[h].textContent}",`);
                                  l = l.trim().substring(0, l.length - 1),
                                  l += "),"
                              }
                              l = l.trim().substring(0, l.length - 1),
                              l += ";",
                              o.download && (l = `data:application/sql;charset=utf-8,${l}`)
                          } else if ("json" === o.type) {
                              for (h = 0; h < a.length; h++)
                                  for (i[h] = i[h] || {}, n = 0; n < s.length; n++)
                                      !o.skipColumn.includes(s[n].originalCellIndex) && this.columns(s[n].originalCellIndex).visible() && (i[h][s[n].textContent] = a[h].cells[n].textContent);
                              l = JSON.stringify(i, o.replacer, o.space),
                              o.download && (l = `data:application/json;charset=utf-8,${l}`)
                          }
                          return o.download && (o.filename = o.filename || "datatable_export", o.filename += `.${o.type}`, l = encodeURI(l), r = document.createElement("a"), r.href = l, r.download = o.filename, document.body.appendChild(r), r.click(), document.body.removeChild(r)), l
                      }
                  }
                  return !1
              }
              import(e)
              {
                  let s = !1;
                  if (!t(e))
                      return !1;
                  const a = {
                      lineDelimiter: "\n",
                      columnDelimiter: ",",
                      ...e
                  };
                  if (a.data.length || t(a.data)) {
                      if ("csv" === a.type) {
                          s = {
                              data: []
                          };
                          const t = a.data.split(a.lineDelimiter);
                          t.length && (a.headings && (s.headings = t[0].split(a.columnDelimiter), t.shift()), t.forEach(((t, e) => {
                              s.data[e] = [];
                              const i = t.split(a.columnDelimiter);
                              i.length && i.forEach((t => {
                                  s.data[e].push(t)
                              }))
                          })))
                      } else if ("json" === a.type) {
                          const e = (e => {
                              let s = !1;
                              try {
                                  s = JSON.parse(e)
                              } catch (t) {
                                  return !1
                              }
                              return !(null === s || !Array.isArray(s) && !t(s)) && s
                          })(a.data);
                          e && (s = {
                              headings: [],
                              data: []
                          }, e.forEach(((t, e) => {
                              s.data[e] = [],
                              Object.entries(t).forEach((([t, a]) => {
                                  s.headings.includes(t) || s.headings.push(t),
                                  s.data[e].push(a)
                              }))
                          })))
                      }
                      t(a.data) && (s = a.data),
                      s && this.insert(s)
                  }
                  return !1
              }
              print()
              {
                  const t = this.activeHeadings,
                      s = this.activeRows,
                      a = e("table"),
                      i = e("thead"),
                      n = e("tbody"),
                      h = e("tr");
                  t.forEach((t => {
                      h.appendChild(e("th", {
                          html: t.textContent
                      }))
                  })),
                  i.appendChild(h),
                  s.forEach((t => {
                      const s = e("tr");
                      Array.from(t.cells).forEach((t => {
                          s.appendChild(e("td", {
                              html: t.textContent
                          }))
                      })),
                      n.appendChild(s)
                  })),
                  a.appendChild(i),
                  a.appendChild(n);
                  const l = window.open();
                  l.document.body.appendChild(a),
                  l.print()
              }
              setMessage(t)
              {
                  let s = 1;
                  this.hasRows ? s = this.data[0].cells.length : this.activeHeadings.length && (s = this.activeHeadings.length),
                  this.wrapper.classList.add("dataTable-empty"),
                  this.label && (this.label.innerHTML = ""),
                  this.totalPages = 0,
                  this.render("pager"),
                  this.clear(e("tr", {
                      html: `<td class="dataTables-empty" colspan="${s}">${t}</td>`
                  }))
              }
              columns(t)
              {
                  return new h(this, t)
              }
              rows(t)
              {
                  return new n(this, t)
              }
              on(t, e)
              {
                  this.events = this.events || {},
                  this.events[t] = this.events[t] || [],
                  this.events[t].push(e)
              }
              off(t, e)
              {
                  this.events = this.events || {},
                  t in this.events != !1 && this.events[t].splice(this.events[t].indexOf(e), 1)
              }
              emit(t)
              {
                  if (this.events = this.events || {}, t in this.events != !1)
                      for (let e = 0; e < this.events[t].length; e++)
                          this.events[t][e].apply(this, Array.prototype.slice.call(arguments, 1))
              }
          }
          exports.DataTable = o;


      }, {
          "./date-cd1c23ce.js": 1
      }]
  }, {}, [2])(2)
});
