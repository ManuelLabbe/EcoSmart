#include "sensor_transformer.h"
#include "transformer_weights.h"
#include <math.h>
#include <string.h>
#include <float.h>

/* ── Buffers estáticos de activaciones ────────────────────────────────────────
   Tamaños máximos para T=20, d_model=64, dim_ff=256, n_heads=4, head_dim=16  */
static float s_h[ST_WINDOW][ST_D_MODEL];        /* activación principal       */
static float s_tmp[ST_WINDOW][ST_D_MODEL];       /* temporal para residual     */
static float s_Q[ST_WINDOW][ST_D_MODEL];
static float s_K[ST_WINDOW][ST_D_MODEL];
static float s_V[ST_WINDOW][ST_D_MODEL];
static float s_attn[ST_WINDOW][ST_WINDOW];       /* scores de atención (T×T)   */
static float s_ff[ST_WINDOW][ST_DIM_FF];         /* FFN capa 1                 */
static float s_pooled[ST_D_MODEL];               /* mean pool                  */
static float s_cls_mid[32];                      /* salida linear 64→32        */

/* Buffer circular de muestras */
static st_sample_t s_window[ST_WINDOW];
static int s_count = 0;   /* muestras acumuladas */
static int s_head  = 0;   /* índice de escritura en el buffer circular */

/* ── Primitivas ───────────────────────────────────────────────────────────────*/

/* y[i] = sum_k x[i*Kx + k] * W[i_out*K_in + k] + b[i_out]
   x: (M, K), W: (N, K) → y: (M, N)  */
static void matmul(const float *x, const float *W, const float *b,
                   float *y, int M, int K, int N)
{
    for (int i = 0; i < M; i++) {
        for (int j = 0; j < N; j++) {
            float s = b ? b[j] : 0.0f;
            for (int k = 0; k < K; k++)
                s += x[i * K + k] * W[j * K + k];
            y[i * N + j] = s;
        }
    }
}

static void layer_norm(float *x, const float *gamma, const float *beta, int T, int D)
{
    for (int t = 0; t < T; t++) {
        float mean = 0.f, var = 0.f;
        for (int d = 0; d < D; d++) mean += x[t * D + d];
        mean /= D;
        for (int d = 0; d < D; d++) { float v = x[t*D+d]-mean; var += v*v; }
        var /= D;
        float inv = 1.f / sqrtf(var + 1e-5f);
        for (int d = 0; d < D; d++)
            x[t * D + d] = ((x[t * D + d] - mean) * inv) * gamma[d] + beta[d];
    }
}

static void softmax_row(float *x, int N)
{
    float mx = -FLT_MAX;
    for (int i = 0; i < N; i++) if (x[i] > mx) mx = x[i];
    float s = 0.f;
    for (int i = 0; i < N; i++) { x[i] = expf(x[i] - mx); s += x[i]; }
    for (int i = 0; i < N; i++) x[i] /= s;
}

static float sigmoid(float x) { return 1.f / (1.f + expf(-x)); }

/* GELU exacto: x * 0.5 * (1 + erf(x / sqrt(2))) */
static float gelu(float x) { return x * 0.5f * (1.f + erff(x * 0.7071067811865476f)); }

/* ── Multi-head self-attention ───────────────────────────────────────────────*/
static void mha(const float *x,
                const float *qkv_w, const float *qkv_b,
                const float *out_w, const float *out_b,
                float *y, int T)
{
    const int D = ST_D_MODEL, H = ST_N_HEADS, Hd = ST_HEAD_DIM;
    const float scale = 1.f / sqrtf((float)Hd);

    /* Proyectar Q, K, V en paralelo usando in_proj_weight (3D, D) */
    matmul(x, qkv_w,           qkv_b,           (float*)s_Q, T, D, D);
    matmul(x, qkv_w + D*D,     qkv_b + D,       (float*)s_K, T, D, D);
    matmul(x, qkv_w + 2*D*D,   qkv_b + 2*D,     (float*)s_V, T, D, D);

    /* Por cada cabeza de atención */
    memset(s_tmp, 0, sizeof(s_tmp));
    for (int h = 0; h < H; h++) {
        int off = h * Hd;
        /* Scores: Q_h @ K_h^T * scale */
        for (int i = 0; i < T; i++) {
            for (int j = 0; j < T; j++) {
                float dot = 0.f;
                for (int k = 0; k < Hd; k++)
                    dot += s_Q[i][off+k] * s_K[j][off+k];
                s_attn[i][j] = dot * scale;
            }
            softmax_row(s_attn[i], T);
        }
        /* Contexto: attn @ V_h → acumula en s_tmp */
        for (int i = 0; i < T; i++)
            for (int k = 0; k < Hd; k++) {
                float v = 0.f;
                for (int j = 0; j < T; j++) v += s_attn[i][j] * s_V[j][off+k];
                s_tmp[i][off+k] = v;
            }
    }
    /* Proyección de salida */
    matmul((float*)s_tmp, out_w, out_b, y, T, D, D);
}

/* Buffers adicionales para encoder_layer — estáticos para no reventar el stack */
static float s_attn_out[ST_WINDOW * ST_D_MODEL];
static float s_ff_in[ST_WINDOW * ST_D_MODEL];

/* ── Encoder layer (pre-LN) ──────────────────────────────────────────────────*/
static void encoder_layer(
    float *x,                          /* (T, D) in/out */
    const float *qkv_w, const float *qkv_b,
    const float *out_w, const float *out_b,
    const float *ff1_w, const float *ff1_b,
    const float *ff2_w, const float *ff2_b,
    const float *n1_w,  const float *n1_b,
    const float *n2_w,  const float *n2_b,
    int T)
{
    const int D = ST_D_MODEL;

    /* Sub-layer 1: pre-LN + self-attention + residual */
    memcpy(s_attn_out, x, T * D * sizeof(float));
    layer_norm(s_attn_out, n1_w, n1_b, T, D);
    mha(s_attn_out, qkv_w, qkv_b, out_w, out_b, s_attn_out, T);
    for (int i = 0; i < T * D; i++) x[i] += s_attn_out[i];

    /* Sub-layer 2: pre-LN + FFN + residual */
    memcpy(s_ff_in, x, T * D * sizeof(float));
    layer_norm(s_ff_in, n2_w, n2_b, T, D);
    matmul(s_ff_in, ff1_w, ff1_b, (float*)s_ff, T, D, ST_DIM_FF);
    for (int i = 0; i < T * ST_DIM_FF; i++) ((float*)s_ff)[i] = gelu(((float*)s_ff)[i]);
    matmul((float*)s_ff, ff2_w, ff2_b, s_ff_in, T, ST_DIM_FF, D);
    for (int i = 0; i < T * D; i++) x[i] += s_ff_in[i];
}

/* Buffer normalización — estático para no usar stack */
static float s_x_norm[ST_WINDOW * ST_N_FEATURES];

/* ── Forward pass completo ───────────────────────────────────────────────────*/
static void forward(const float input[ST_WINDOW][ST_N_FEATURES], st_result_t *out)
{
    const int T = ST_WINDOW, D = ST_D_MODEL;

    /* 1. Normalizar input */
    float (*x_norm)[ST_N_FEATURES] = (float(*)[ST_N_FEATURES])s_x_norm;
    for (int t = 0; t < T; t++)
        for (int f = 0; f < ST_N_FEATURES; f++)
            x_norm[t][f] = (input[t][f] - ST_NORM_MEAN[f]) / ST_NORM_STD[f];

    /* 2. Input projection (T, 6) → (T, 64) */
    matmul((float*)x_norm, ST_INPUT_PROJ_W, ST_INPUT_PROJ_B, (float*)s_h, T, ST_N_FEATURES, D);

    /* 3. Positional encoding */
    for (int t = 0; t < T; t++)
        for (int d = 0; d < D; d++)
            s_h[t][d] += ST_POS_ENC[t * D + d];

    /* 4. Tres encoder layers */
    #define EL(i) encoder_layer( \
        (float*)s_h, \
        ST_L##i##_QKV_W, ST_L##i##_QKV_B, \
        ST_L##i##_OUTPROJ_W, ST_L##i##_OUTPROJ_B, \
        ST_L##i##_FF1_W, ST_L##i##_FF1_B, \
        ST_L##i##_FF2_W, ST_L##i##_FF2_B, \
        ST_L##i##_NORM1_W, ST_L##i##_NORM1_B, \
        ST_L##i##_NORM2_W, ST_L##i##_NORM2_B, T)
    EL(0); EL(1); EL(2);
    #undef EL

    /* 5. Final LayerNorm */
    layer_norm((float*)s_h, ST_NORM_W, ST_NORM_B, T, D);

    /* 6. Mean pooling (T, D) → (D,) */
    memset(s_pooled, 0, sizeof(s_pooled));
    for (int t = 0; t < T; t++)
        for (int d = 0; d < D; d++)
            s_pooled[d] += s_h[t][d];
    for (int d = 0; d < D; d++) s_pooled[d] /= T;

    /* 7. Classifier: Linear(64→32) + GELU + Linear(32→5) */
    matmul(s_pooled, ST_CLS0_W, ST_CLS0_B, s_cls_mid, 1, D, 32);
    for (int i = 0; i < 32; i++) s_cls_mid[i] = gelu(s_cls_mid[i]);
    float logits[ST_N_LABELS];
    matmul(s_cls_mid, ST_CLS3_W, ST_CLS3_B, logits, 1, 32, ST_N_LABELS);

    /* 8. Sigmoid → probabilidades */
    float probs[ST_N_LABELS];
    float max_p = 0.f;
    for (int i = 0; i < ST_N_LABELS; i++) {
        probs[i] = sigmoid(logits[i]);
        if (probs[i] > max_p) max_p = probs[i];
    }

    out->twf = probs[0]; out->hdf = probs[1]; out->pwf = probs[2];
    out->osf = probs[3]; out->rnf = probs[4];
    out->anomaly_score      = max_p;
    out->predicted_failure  = (max_p >= 0.5f) ? 1 : 0;
}

/* ── API pública ──────────────────────────────────────────────────────────────*/

void st_init(void)
{
    s_count = 0;
    s_head  = 0;
    memset(s_window, 0, sizeof(s_window));
}

int st_push_and_infer(const st_sample_t *sample, st_result_t *result)
{
    s_window[s_head] = *sample;
    s_head = (s_head + 1) % ST_WINDOW;
    if (s_count < ST_WINDOW) s_count++;
    if (s_count < ST_WINDOW) return 0;

    /* Reordenar buffer circular → secuencia cronológica */
    float input[ST_WINDOW][ST_N_FEATURES];
    for (int t = 0; t < ST_WINDOW; t++) {
        int idx = (s_head + t) % ST_WINDOW;
        input[t][0] = s_window[idx].air_temp_k;
        input[t][1] = s_window[idx].process_temp_k;
        input[t][2] = s_window[idx].rpm;
        input[t][3] = s_window[idx].torque_nm;
        input[t][4] = s_window[idx].tool_wear_min;
        input[t][5] = s_window[idx].type_enc;
    }
    forward(input, result);
    return 1;
}
