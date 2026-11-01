/* Sample-size formulas for common study designs. Pure functions, no DOM.
   Normal-approximation methods as in Chow, Shao & Wang (Sample Size Calculations in Clinical Research),
   Fleiss (Statistical Methods for Rates and Proportions) and Lwanga & Lemeshow (WHO). */
(function (root) {
  /* inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9) */
  function z(p) {
    var a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
    var b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01];
    var c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
    var d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00];
    var pl = 0.02425, q, r;
    if (p <= 0 || p >= 1) return NaN;
    if (p < pl) { q = Math.sqrt(-2 * Math.log(p)); return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    if (p > 1 - pl) { q = Math.sqrt(-2 * Math.log(1 - p)); return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); }
    q = p - 0.5; r = q * q;
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  }
  var ca = function (alpha, sides) { return z(1 - alpha / sides); };
  var cb = function (power) { return z(power); };
  var up = Math.ceil;

  /* every design returns { n1, n2 } = participants needed (before dropout) in group 1 and 2 */
  var designs = {
    /* two independent means: sd = common SD, delta = difference to detect, k = n2/n1 */
    twoMeans: function (o) {
      var za = ca(o.alpha, o.sides), zb = cb(o.power), k = o.ratio || 1;
      var n1 = (1 + 1 / k) * Math.pow(o.sd * (za + zb) / o.delta, 2) + za * za / 4;  /* small-sample correction */
      return { n1: up(n1), n2: up(k * n1), groups: 2 };
    },
    /* two independent proportions p1 vs p2 */
    twoProps: function (o) {
      var za = ca(o.alpha, o.sides), zb = cb(o.power), k = o.ratio || 1, p1 = o.p1, p2 = o.p2;
      var pbar = (p1 + k * p2) / (1 + k), qbar = 1 - pbar;
      var n1 = Math.pow(za * Math.sqrt((1 + 1 / k) * pbar * qbar) + zb * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2) / k), 2) / Math.pow(p1 - p2, 2);
      return { n1: up(n1), n2: up(k * n1), groups: 2 };
    },
    /* single proportion (prevalence): expected p, absolute precision d, optional finite population N */
    oneProp: function (o) {
      var za = z(1 - o.alpha / 2), n = za * za * o.p * (1 - o.p) / (o.d * o.d);
      if (o.N) n = n / (1 + (n - 1) / o.N);
      return { n1: up(n), n2: 0, groups: 1 };
    },
    /* paired means: sdDiff = SD of the within-pair differences */
    paired: function (o) {
      var za = ca(o.alpha, o.sides), zb = cb(o.power);
      var n = Math.pow(o.sdDiff * (za + zb) / o.delta, 2) + za * za / 2;
      return { n1: up(n), n2: 0, groups: 1 };
    },
    /* correlation: smallest r worth detecting (Fisher z) */
    corr: function (o) {
      var za = ca(o.alpha, o.sides), zb = cb(o.power), C = 0.5 * Math.log((1 + o.r) / (1 - o.r));
      return { n1: up(Math.pow((za + zb) / C, 2) + 3), n2: 0, groups: 1 };
    }
  };

  /* inflate for expected dropout / non-response */
  function withDropout(n, drop) { return drop > 0 ? Math.ceil(n / (1 - drop)) : n; }

  var api = { z: z, designs: designs, withDropout: withDropout };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.SS = api;
})(typeof window !== "undefined" ? window : this);
